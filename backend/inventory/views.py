# inventory/views.py

import re
from decimal import Decimal
from django.db import connection, transaction
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

from rest_framework import status, viewsets, mixins
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication

from rapidfuzz import process, fuzz

from .models import Item, Location, Bin, ReorderPolicy, StockLedger, Inventory, ItemAlias
from .serializers import (
    ItemSerializer, LocationSerializer, BinSerializer,
    ReorderPolicySerializer, StockLedgerSerializer, InventorySerializer
)
from .utils import speak

# ------------------- Auth ----------------------------#

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
        })

class LogoutView(APIView):
    """
    Erwartet im Body den refresh-Token und blacklisted ihn.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            # Auch wenn etwas schief geht, kein Leaken von Details
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
# ------------------- Fuzzy Kandidaten -------------------

def fuzzy_candidates(q: str, limit: int = 5):
    items = list(Item.objects.all().values("id", "sku", "name"))
    aliases = list(ItemAlias.objects.select_related("item").values("item_id", "alias"))
    by_id = {i["id"]: i for i in items}

    entries = []
    entries += [(str(i["sku"]), i["id"]) for i in items if i["sku"]]
    entries += [(str(i["name"]), i["id"]) for i in items if i["name"]]
    entries += [(str(a["alias"]), a["item_id"]) for a in aliases if a["alias"]]

    if not entries:
        return []

    texts = [t for (t, _id) in entries]
    results = process.extract(q, texts, scorer=fuzz.WRatio, limit=limit * 3)

    seen, out = set(), []
    for choice_text, score, idx in results:
        item_id = entries[idx][1]
        if item_id in seen:
            continue
        seen.add(item_id)
        info = by_id.get(item_id)
        if not info:
            continue
        out.append({
            "sku": info["sku"],
            "name": info["name"],
            "score": round(float(score) / 100.0, 3),
        })
        if len(out) >= limit:
            break
    return out


# ------------------- ViewSets (CRUD) -------------------

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().order_by("sku")
    serializer_class = ItemSerializer
    permission_classes = [AllowAny]
    search_fields = ["sku", "name"]


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all().order_by("code")
    serializer_class = LocationSerializer
    permission_classes = [AllowAny]


class BinViewSet(viewsets.ModelViewSet):
    queryset = Bin.objects.select_related("location").all().order_by("location__code", "code")
    serializer_class = BinSerializer
    permission_classes = [AllowAny]


class ReorderPolicyViewSet(viewsets.ModelViewSet):
    queryset = ReorderPolicy.objects.select_related("item", "location").all()
    serializer_class = ReorderPolicySerializer
    permission_classes = [AllowAny]


class StockLedgerViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    queryset = StockLedger.objects.select_related("item", "from_bin", "to_bin").all().order_by("-ts")
    serializer_class = StockLedgerSerializer
    permission_classes = [AllowAny]


class InventoryViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = Inventory.objects.select_related("item", "bin", "bin__location").all()
    serializer_class = InventorySerializer
    permission_classes = [AllowAny]


# ------------------- Health -------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return JsonResponse({"status": "ok"})


# ------------------- Bin-Normalisierung & -Auflösung -------------------

def normalize_bin_input(s):
    if not isinstance(s, str):
        # Debug-Log, damit du später siehst, was schief läuft
        import logging
        logging.error(f"normalize_bin_input called with non-string: {type(s)} -> {s}")
        return None
    t = s.strip()
    t = re.sub(r'^\s*bin\s+', '', t, flags=re.I)
    t = re.sub(r'[\s_]+', '-', t)
    t = re.sub(r'-{2,}', '-', t)
    return t.strip()



def resolve_bin(code_raw: str) -> Bin:
    """
    Sucht Bin:
      1) Exakt <LOC>-<BIN>
      2) Falls kein LOC: nimmt MAIN als Default
      3) Teilstring-Suche (erst in MAIN, sonst global)
    """
    if not isinstance(code_raw, str):
        raise Http404("Kein Lagerplatz angegeben.")

    code = normalize_bin_input(code_raw)
    if not code:
        raise Http404("Kein Lagerplatz angegeben.")

    parts = code.split('-')

    # 1) Vollständiger Location+Bin-Code
    if len(parts) >= 4:
        loc_code = parts[0]
        bin_code = "-".join(parts[1:])
        try:
            loc = Location.objects.get(code=loc_code)
            return Bin.objects.get(location=loc, code=bin_code)
        except (Location.DoesNotExist, Bin.DoesNotExist):
            pass

    # 2) Default-Location MAIN
    try:
        main = Location.objects.get(code="MAIN")
        bin_obj = Bin.objects.filter(location=main, code=code).first()
        if bin_obj:
            return bin_obj
        # 3) Teilstring-Suche
        bin_obj = (Bin.objects.filter(location=main, code__icontains=code).first()
                   or Bin.objects.filter(code__icontains=code).first())
        if bin_obj:
            return bin_obj
    except Location.DoesNotExist:
        pass

    # Kein Treffer
    raise Http404(f"Bin {code_raw} nicht gefunden.")



@api_view(["GET"])
@permission_classes([AllowAny])
def resolve_item(request):
    """
    GET /api/resolve-item?q=<free text or sku>
    Liefert Kandidaten im Format:
    { "data": { "candidates": [ {sku, name, score}, ... ] } }
    """
    q = (request.query_params.get("q") or "").strip()
    if not q:
        return Response({"data": {"candidates": []}}, status=400)
    cands = fuzzy_candidates(q, limit=5)
    return Response({"data": {"candidates": cands}})


# ------------------- Bestand / Stock -------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def stock(request):
    """
    GET /api/stock?sku=SKU
    Liefert { bins: [{bin, location, qty}], on_hand, sku, name }
    """
    sku = (request.query_params.get("sku") or "").strip()
    if not sku:
        return speak({"bins": []}, "SKU erforderlich.", http_status=400)

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        cands = fuzzy_candidates(sku)
        if cands:
            speech = (
                f'Meinst du {cands[0]["sku"]} – {cands[0]["name"]}?'
                if cands[0]["score"] < 0.9 else
                f'{cands[0]["sku"]} – {cands[0]["name"]} gefunden.'
            )
            return speak({"candidates": cands}, speech, http_status=200)
        return speak({"bins": []}, f"SKU {sku} nicht gefunden.", http_status=404)

    rows = (
        Inventory.objects
        .filter(item=item)
        .select_related("bin__location")
        .values("bin__code", "bin__location__code", "qty")
    )
    bins = [{"bin": r["bin__code"], "location": r["bin__location__code"], "qty": r["qty"]} for r in rows]
    on_hand = sum([r["qty"] for r in rows]) if rows else Decimal("0")
    speech = (
        f"{item.sku} – {item.name}: Bestand {on_hand} {item.uom}. "
        + (f"In {len(bins)} Bins." if bins else "Keine Lagerplätze gefunden.")
    )
    return speak({"bins": bins, "on_hand": str(on_hand), "sku": item.sku, "name": item.name}, speech)


# ------------------- Reorder -------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def reorder_suggestions(request):
    """
    GET /api/reorder/suggestions
    Liefert Liste mit (sku, name, location, on_hand, reorder_point, suggested_qty)
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT rp.item_id, rp.location_id,
                   COALESCE(SUM(inv.qty), 0) AS on_hand,
                   rp.reorder_point, rp.reorder_qty,
                   GREATEST(rp.reorder_qty,
                            rp.reorder_point - COALESCE(SUM(inv.qty),0)) AS suggested_qty
            FROM inventory_reorderpolicy rp
            LEFT JOIN inventory_inventory inv ON inv.item_id = rp.item_id
            LEFT JOIN inventory_bin b ON b.id = inv.bin_id
            WHERE (rp.location_id IS NULL OR b.location_id = rp.location_id)
            GROUP BY rp.item_id, rp.location_id, rp.reorder_point, rp.reorder_qty
            HAVING COALESCE(SUM(inv.qty),0) <= rp.reorder_point;
        """)
        cols = [c[0] for c in cur.description]
        data = [dict(zip(cols, row)) for row in cur.fetchall()]

    items = {i.id: i for i in Item.objects.filter(id__in=[d["item_id"] for d in data])}
    locs = {l.id: l for l in Location.objects.all()}

    out = [{
        "sku": items[d["item_id"]].sku,
        "name": items[d["item_id"]].name,
        "location": (locs[d["location_id"]].code if d["location_id"] else "ALL"),
        "on_hand": float(d["on_hand"]),
        "reorder_point": float(d["reorder_point"]),
        "suggested_qty": float(d["suggested_qty"]),
    } for d in data]

    return Response(out)


# ------------------- Aktionen: Wareneingang / Umlagerung / Entnahme -------------------

@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_exempt
@transaction.atomic
def receive_goods(request):
    """
    POST /api/stock/receive
    Body: { "sku": "...", "qty": 5, "bin": "A-01-01", "ref_id": "..."? }
    """
    sku = request.data.get("sku")
    qty = request.data.get("qty")
    bin_code = request.data.get("bin")
    ref_id = request.data.get("ref_id") or ""

    if not all([sku, qty, bin_code]):
        return Response({"error": "sku, qty, bin required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError
    except Exception:
        return Response({"error": "qty must be positive number"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        return speak({"status": "error"}, f"SKU {sku} nicht gefunden.", http_status=404)

    try:
        b = resolve_bin(bin_code)
    except Http404 as e:
        return speak({"status": "error"}, str(e), http_status=404)

    StockLedger.objects.create(item=item, to_bin=b, qty=qty, ref_type="PO_RECEIPT", ref_id=ref_id)

    inv, created = Inventory.objects.get_or_create(item=item, bin=b, defaults={"qty": qty})
    if not created:
        inv.qty = inv.qty + qty
        inv.save()

    return speak(
        {"status": "ok", "new_bin_qty": str(inv.qty)},
        f"Eingang gebucht: {qty} {item.uom} für {item.sku} in {b.location.code}-{b.code}."
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_exempt
@transaction.atomic
def move_goods(request):
    """
    POST /api/stock/move/
    Body: { "sku": "...", "qty": 10, "from_bin": "A-01-01", "to_bin": "A-01-02", "ref_id": "..."? }
    """
    sku       = request.data.get("sku")
    qty_raw   = request.data.get("qty")
    from_code = request.data.get("from_bin")
    to_code   = request.data.get("to_bin")
    ref_id    = request.data.get("ref_id") or ""  # niemals NULL speichern

    # Pflichtfelder prüfen
    if not all([sku, qty_raw, from_code, to_code]):
        return Response({"error": "sku, qty, from_bin, to_bin required"}, status=400)

    # qty sicher parsen
    try:
        qty = Decimal(str(qty_raw))
        if qty <= 0:
            raise ValueError
    except Exception:
        return Response({"error": "qty must be positive number"}, status=400)

    # Artikel holen
    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        return speak({"status": "error"}, f"SKU {sku} nicht gefunden.", http_status=404)

    # Bins robust auflösen (unterstützt LOC-BIN, MAIN-Default, Teilstring)
    try:
        b_from = resolve_bin(from_code)
    except Http404 as e:
        return speak({"status": "error"}, str(e), http_status=404)

    try:
        b_to = resolve_bin(to_code)
    except Http404 as e:
        return speak({"status": "error"}, str(e), http_status=404)

    # Bestand im from_bin prüfen
    inv_from, _ = Inventory.objects.get_or_create(item=item, bin=b_from, defaults={"qty": Decimal("0")})
    if inv_from.qty < qty:
        return Response(
            {"error": "insufficient stock in from_bin", "available": str(inv_from.qty)},
            status=400
        )

    # Ledger schreiben
    StockLedger.objects.create(
        item=item,
        from_bin=b_from,
        to_bin=b_to,
        qty=qty,
        ref_type="MOVE",
        ref_id=ref_id,
    )

    # Bestände buchen
    inv_from.qty = inv_from.qty - qty
    inv_from.save()

    inv_to, created = Inventory.objects.get_or_create(item=item, bin=b_to, defaults={"qty": qty})
    if not created:
        inv_to.qty = inv_to.qty + qty
        inv_to.save()

    # Sprach-/Frontend-Antwort
    return speak(
        {
            "status": "ok",
            "from_bin_qty": str(inv_from.qty),
            "to_bin_qty": str(inv_to.qty),
            "sku": item.sku
        },
        f"Umgebucht: {qty} {item.uom} von {b_from.location.code}-{b_from.code} nach {b_to.location.code}-{b_to.code}."
    )



@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_exempt
@transaction.atomic
def issue_goods(request):
    """
    POST /api/stock/issue
    Body: { "sku": "M4-12", "qty": 5, "from_bin": "A-01-01", "ref_id": "ISSUE-123"? }
    """
    sku = request.data.get("sku")
    qty = request.data.get("qty")
    from_code = request.data.get("from_bin")
    ref_id = request.data.get("ref_id") or ""  # nie NULL speichern

    if not all([sku, qty, from_code]):
        return Response({"error": "sku, qty, from_bin required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError
    except Exception:
        return Response({"error": "qty must be positive number"}, status=status.HTTP_400_BAD_REQUEST)

    item = get_object_or_404(Item, sku=sku)

    # Bin auflösen + Bestand prüfen
    try:
        b_from = resolve_bin(from_code)
    except Http404 as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    inv_from, _ = Inventory.objects.get_or_create(item=item, bin=b_from, defaults={"qty": 0})
    if inv_from.qty < qty:
        return Response({"error": "insufficient stock in from_bin", "available": str(inv_from.qty)},
                        status=status.HTTP_400_BAD_REQUEST)

    # Ledger buchen
    StockLedger.objects.create(
        item=item,
        from_bin=b_from,
        to_bin=None,
        qty=qty,
        ref_type="ISSUE",
        ref_id=ref_id,
    )

    # Bestand reduzieren
    inv_from.qty = inv_from.qty - qty
    inv_from.save()

    return speak(
        {"status": "ok", "from_bin_qty": str(inv_from.qty)},
        f"Entnahme gebucht: {qty} {item.uom} von {b_from.location.code}-{b_from.code}."
    )


# ------------------- Bewegungen -------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def stock_moves(request):
    """
    GET /api/stock-moves?sku=SKU&limit=5
    Liefert { rows: [...] } mit jüngsten Bewegungen
    """
    sku = (request.query_params.get("sku") or "").strip()
    limit = int(request.query_params.get("limit", 5))
    if not sku:
        return speak({"rows": []}, "Bitte eine SKU angeben.", http_status=400)

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        cands = fuzzy_candidates(sku)
        if cands:
            speech = (
                f'Meinst du {cands[0]["sku"]} – {cands[0]["name"]}?'
                if cands[0]["score"] < 0.9 else
                f'{cands[0]["sku"]} – {cands[0]["name"]} gefunden.'
            )
            return speak({"candidates": cands}, speech, http_status=200)
        return speak({"rows": []}, f"SKU {sku} nicht gefunden.", http_status=404)

    qs = (StockLedger.objects
          .filter(item=item)
          .select_related("from_bin__location", "to_bin__location")
          .order_by("-ts")[:limit])

    rows = [{
        "ts": sl.ts.isoformat(),
        "qty": float(sl.qty),
        "from_bin": (f"{sl.from_bin.location.code}-{sl.from_bin.code}" if sl.from_bin else None),
        "to_bin": (f"{sl.to_bin.location.code}-{sl.to_bin.code}" if sl.to_bin else None),
        "ref_type": sl.ref_type,
        "ref_id": sl.ref_id,
    } for sl in qs]

    if not rows:
        return speak({"rows": []}, f"Keine Bewegungen für {item.sku} gefunden.")

    last = rows[0]
    dirn = (f'von {last["from_bin"]} nach {last["to_bin"]}'
            if last["from_bin"] and last["to_bin"]
            else f'nach {last["to_bin"]}' if last["to_bin"]
            else f'von {last["from_bin"]}' if last["from_bin"] else "gebucht")
    speech = f"Letzte {len(rows)} Bewegungen für {item.sku}. Zuletzt {last['qty']} {item.uom} {dirn}."
    return speak({"rows": rows}, speech)


