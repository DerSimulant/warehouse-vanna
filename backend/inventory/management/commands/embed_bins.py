from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.conf import settings
from inventory.models import Bin
from inventory.utils_embeddings import embed_text

VECTOR_DIM = getattr(settings, "EMBEDDING_DIM", 1536)  # anpassen

class Command(BaseCommand):
    help = "Erzeugt/aktualisiert Embeddings für alle Bins (pgvector)."

    def handle(self, *args, **opts):
        total = Bin.objects.count()
        updated = 0

        # Speicherfreundlich iterieren
        for b in Bin.objects.select_related("location").iterator(chunk_size=500):
            loc = (getattr(b.location, "code", "") or "").strip()
            code = (b.code or "").strip()
            if not loc and not code:
                continue

            full = f"{loc}-{code}".strip("-")
            parts = [
                loc, code, full,
                loc.replace("-", " "), code.replace("-", " "), full.replace("-", " "),
                "lagerplatz fach regal bin platz",
            ]
            text = " ".join(p for p in parts if p).strip()

            vec = embed_text(text)  # sollte eine Sequenz aus floats der Länge VECTOR_DIM liefern
            if not vec:
                continue

            # robust casten + Dimension prüfen
            try:
                vec_list = [float(x) for x in vec]
            except Exception:
                continue

            if len(vec_list) != VECTOR_DIM:
                self.stdout.write(self.style.WARNING(
                    f"Übersprungen (Dim): Bin {b.pk} hat {len(vec_list)} statt {VECTOR_DIM}"
                ))
                continue

            b.embedding = vec_list
            b.save(update_fields=["embedding"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Bins: {updated}/{total} Embeddings gespeichert."))

        # pgvector-Index (cosine). Voraussetzung: CREATE EXTENSION vector; einmalig in der DB ausführen.
        # Heuristik für lists: ~4 * sqrt(n)
        lists = max(4, int(4 * (max(total, 1) ** 0.5)))
        with connection.cursor() as cur, transaction.atomic():
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_bin_embedding_ivfflat
                ON inventory_bin
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = %s);
            """, [lists])
            # Planner-Statistiken aktualisieren
            cur.execute("ANALYZE inventory_bin;")

        self.stdout.write(self.style.SUCCESS("ANN-Index geprüft/erstellt und ANALYZE ausgeführt."))
