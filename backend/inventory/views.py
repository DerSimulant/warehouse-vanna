from decimal import Decimal
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from rest_framework import viewsets, mixins
from rest_framework.permissions import AllowAny
from .models import Item, Location, Bin, ReorderPolicy, StockLedger, Inventory
from .serializers import (
    ItemSerializer, LocationSerializer, BinSerializer,
    ReorderPolicySerializer, StockLedgerSerializer, InventorySerializer
)




# Volle CRUD:
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
    queryset = Bin.objects.select_related("location").all().order_by("location__code","code")
    serializer_class = BinSerializer
    permission_classes = [AllowAny]

class ReorderPolicyViewSet(viewsets.ModelViewSet):
    queryset = ReorderPolicy.objects.select_related("item","location").all()
    serializer_class = ReorderPolicySerializer
    permission_classes = [AllowAny]

# Ledger lieber nur lesen (Buchungen erfolgen über Endpunkte):
class StockLedgerViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    queryset = StockLedger.objects.select_related("item","from_bin","to_bin").all().order_by("-ts")
    serializer_class = StockLedgerSerializer
    permission_classes = [AllowAny]

# Inventory i. d. R. auch read-only (wird durch Buchungen gepflegt):
class InventoryViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = Inventory.objects.select_related("item","bin","bin__location").all()
    serializer_class = InventorySerializer
    permission_classes = [AllowAny]

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return JsonResponse({"status": "ok"})

@api_view(["GET"])
@permission_classes([AllowAny])
def stock(request):
    sku = request.query_params.get("sku")
    if not sku:
        return Response({"error": "sku required"}, status=status.HTTP_400_BAD_REQUEST)

    item = get_object_or_404(Item, sku=sku)
    rows = (
        Inventory.objects
        .filter(item=item)
        .select_related("bin__location")
        .values("bin__code", "bin__location__code", "qty")
    )
    bins = [{"bin": r["bin__code"], "location": r["bin__location__code"], "qty": r["qty"]} for r in rows]
    on_hand = sum([r["qty"] for r in rows]) if rows else Decimal("0")
    return Response({"sku": item.sku, "name": item.name, "on_hand": on_hand, "bins": bins})


@api_view(["GET"])
@permission_classes([AllowAny])
def reorder_suggestions(request):
    # Meldemenge unterschritten je (item, location)
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


@api_view(["POST"])
@transaction.atomic
def receive_goods(request):
    # Body: { "sku":"M4-12", "qty":50, "bin":"A-01-01", "ref_id":"PO-123" }
    sku = request.data.get("sku")
    qty = request.data.get("qty")
    bin_code = request.data.get("bin")
    ref_id = request.data.get("ref_id", "")

    if not all([sku, qty, bin_code]):
        return Response({"error": "sku, qty, bin required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError
    except Exception:
        return Response({"error": "qty must be positive number"}, status=status.HTTP_400_BAD_REQUEST)

    item = get_object_or_404(Item, sku=sku)
    try:
        b = Bin.objects.get(code=bin_code)
    except Bin.DoesNotExist:
        return Response({"error": f"bin not found: {bin_code}"}, status=status.HTTP_404_NOT_FOUND)

    # Ledger buchen
    StockLedger.objects.create(item=item, to_bin=b, qty=qty, ref_type="PO_RECEIPT", ref_id=ref_id)

    # Inventory upsert
    inv, created = Inventory.objects.get_or_create(item=item, bin=b, defaults={"qty": qty})
    if not created:
        inv.qty = inv.qty + qty
        inv.save()

    return Response({"status": "ok", "new_bin_qty": str(inv.qty)})

@api_view(["POST"])
@transaction.atomic
def move_goods(request):
    """
    Body: { "sku": "M4-12", "qty": 10, "from_bin": "A-01-01", "to_bin": "A-01-02", "ref_id": "MOVE-123" }
    """
    from decimal import Decimal
    sku = request.data.get("sku")
    qty = request.data.get("qty")
    from_code = request.data.get("from_bin")
    to_code = request.data.get("to_bin")
    ref_id = request.data.get("ref_id", "")

    if not all([sku, qty, from_code, to_code]):
        return Response({"error": "sku, qty, from_bin, to_bin required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError
    except Exception:
        return Response({"error": "qty must be positive number"}, status=status.HTTP_400_BAD_REQUEST)

    item = get_object_or_404(Item, sku=sku)
    try:
        b_from = Bin.objects.get(code=from_code)
    except Bin.DoesNotExist:
        return Response({"error": f"from_bin not found: {from_code}"}, status=status.HTTP_404_NOT_FOUND)
    try:
        b_to = Bin.objects.get(code=to_code)
    except Bin.DoesNotExist:
        return Response({"error": f"to_bin not found: {to_code}"}, status=status.HTTP_404_NOT_FOUND)

    # Bestand in FROM prüfen
    inv_from, _ = Inventory.objects.get_or_create(item=item, bin=b_from, defaults={"qty": 0})
    if inv_from.qty < qty:
        return Response({"error": "insufficient stock in from_bin", "available": str(inv_from.qty)}, status=status.HTTP_400_BAD_REQUEST)

    # Ledger buchen
    StockLedger.objects.create(item=item, from_bin=b_from, to_bin=b_to, qty=qty, ref_type="MOVE", ref_id=ref_id)

    # Bestände anpassen
    inv_from.qty = inv_from.qty - qty
    inv_from.save()
    inv_to, created = Inventory.objects.get_or_create(item=item, bin=b_to, defaults={"qty": qty})
    if not created:
        inv_to.qty = inv_to.qty + qty
        inv_to.save()

    return Response({
        "status": "ok",
        "from_bin_qty": str(inv_from.qty),
        "to_bin_qty": str(inv_to.qty),
    })
