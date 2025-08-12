import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Vanna (OpenAI-LLM + lokaler Vectorstore)
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore

load_dotenv()

# ---- Vanna Setup ----
class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

vn = MyVanna(config={
    "api_key": os.getenv("OPENAI_API_KEY"),
    # optional: "model": "gpt-4o-mini",
    "allow_llm_to_see_data": True,  # hilft beim Plan/SQL
})

# DB verbinden (READ-ONLY-User empfohlen!)
vn.connect_to_postgres(
    host=os.getenv("PGHOST"),
    dbname=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT"),
)

print(">>> 1) Schema-Infos sammeln & generisches Training")
# 1) Generisches Schemaverständnis
df_info = vn.run_sql("SELECT * FROM INFORMATION_SCHEMA.COLUMNS")
plan = vn.get_training_plan_generic(df_info)
vn.train(plan=plan)

# 2) Domänen-Dokumentation (kurz & prägnant)
vn.train(documentation="""
Datenmodell (vereinfacht):
- inventory_item(id, sku UNIQUE, name, description, uom, active)
- inventory_location(id, code UNIQUE, name)
- inventory_bin(id, location_id -> inventory_location.id, code, UNIQUE(location_id, code))
- inventory_inventory(id, item_id -> inventory_item.id, bin_id -> inventory_bin.id, qty)
- inventory_reorderpolicy(id, item_id -> inventory_item.id, location_id -> inventory_location.id, 
                          min_qty, reorder_point, reorder_qty, UNIQUE(item_id, location_id))
- inventory_stockledger(id, ts, item_id -> inventory_item.id, 
                        from_bin_id -> inventory_bin.id NULLABLE, to_bin_id -> inventory_bin.id NULLABLE,
                        qty, ref_type, ref_id)

Hinweise:
- "Bestand je Bin" für eine SKU: item -> inventory -> bin -> location
- "Gesamtbestand" = SUM(inventory.qty) über alle Bins je SKU
- "Bestand je Location" = SUM(inventory.qty) gruppiert nach location
- Aktuelle Unterdeckung/Meldemenge: SUM(inventory.qty) je (item, location) vs. reorderpolicy.reorder_point
- Bewegungen: stockledger (from_bin/to_bin, ts, qty)
- „Was liegt in Bin X?“: inventory -> bin(code = X) -> item
- „Wo liegt SKU Y?“: inventory -> item(sku = Y) -> bin + location
""")

print(">>> 2) Kanonische SQL-Beispiele (konkret + generisch)")

# ---- Hilfsfunktion: safe LIMIT für große Tabellen ----
def limit_clause(n=200):
    try:
        n = int(n)
    except:
        n = 200
    return f" LIMIT {n} "

# ---- 2a) Kanonische, KONKRETE Beispiele (mit M4-12 / ABC-100) ----
vn.train(
    question="Bestand je Bin für SKU M4-12",
    sql=f"""
SELECT b.code AS bin, l.code AS location, inv.qty
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'M4-12'
ORDER BY l.code, b.code
""")

vn.train(
    question="Gesamtbestand (on hand) für SKU M4-12",
    sql="""
SELECT i.sku, COALESCE(SUM(inv.qty),0) AS on_hand
FROM inventory_item i
LEFT JOIN inventory_inventory inv ON inv.item_id = i.id
WHERE i.sku = 'M4-12'
GROUP BY i.sku
""")

vn.train(
    question="Bestand je Location für SKU M4-12",
    sql="""
SELECT l.code AS location, COALESCE(SUM(inv.qty),0) AS on_hand
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'M4-12'
GROUP BY l.code
ORDER BY l.code
""")

vn.train(
    question="Welche Bins enthalten SKU M4-12?",
    sql="""
SELECT l.code AS location, b.code AS bin, inv.qty
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'M4-12'
ORDER BY l.code, b.code
""")

vn.train(
    question="Was liegt im Bin A-01-01?",
    sql=f"""
SELECT i.sku, i.name, inv.qty
FROM inventory_inventory inv
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_item i ON i.id = inv.item_id
WHERE b.code = 'A-01-01'
ORDER BY i.sku
{limit_clause(100)}
""")

vn.train(
    question="Letzte 10 Bewegungen (Ledger) für SKU M4-12",
    sql="""
SELECT sl.ts, i.sku,
       fb.code AS from_bin, tb.code AS to_bin,
       sl.qty, sl.ref_type, sl.ref_id
FROM inventory_stockledger sl
JOIN inventory_item i ON i.id = sl.item_id
LEFT JOIN inventory_bin fb ON fb.id = sl.from_bin_id
LEFT JOIN inventory_bin tb ON tb.id = sl.to_bin_id
WHERE i.sku = 'M4-12'
ORDER BY sl.ts DESC
LIMIT 10
""")

vn.train(
    question="Gesamtbestand (on hand) für SKU ABC-100",
    sql="""
SELECT i.sku, COALESCE(SUM(inv.qty),0) AS on_hand
FROM inventory_item i
LEFT JOIN inventory_inventory inv ON inv.item_id = i.id
WHERE i.sku = 'ABC-100'
GROUP BY i.sku
""")

# ---- 2b) Generische Muster mit Platzhaltern (helfen beim Verallgemeinern) ----
vn.train(
    question="Bestand je Bin für eine beliebige SKU (z.B. SKU123)",
    sql="""
SELECT b.code AS bin, l.code AS location, inv.qty
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'SKU123'
ORDER BY l.code, b.code
""")

vn.train(
    question="Gesamtbestand einer beliebigen SKU (z.B. SKU123)",
    sql="""
SELECT i.sku, COALESCE(SUM(inv.qty),0) AS on_hand
FROM inventory_item i
LEFT JOIN inventory_inventory inv ON inv.item_id = i.id
WHERE i.sku = 'SKU123'
GROUP BY i.sku
""")

vn.train(
    question="Bestand je Location für eine beliebige SKU (z.B. SKU123)",
    sql="""
SELECT l.code AS location, COALESCE(SUM(inv.qty),0) AS on_hand
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'SKU123'
GROUP BY l.code
ORDER BY l.code
""")

vn.train(
    question="Welche Bins enthalten eine beliebige SKU (z.B. SKU123)?",
    sql="""
SELECT l.code AS location, b.code AS bin, inv.qty
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = 'SKU123'
ORDER BY l.code, b.code
""")

vn.train(
    question="Was liegt in einem bestimmten Bin (z.B. BIN123)?",
    sql=f"""
SELECT i.sku, i.name, inv.qty
FROM inventory_inventory inv
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_item i ON i.id = inv.item_id
WHERE b.code = 'BIN123'
ORDER BY i.sku
{limit_clause(200)}
""")

# ---- 2c) Reorder / Unterdeckung ----
vn.train(
    question="Welche SKUs sind unter Meldemenge je Location?",
    sql="""
WITH stock AS (
  SELECT i.id AS item_id, l.id AS location_id, COALESCE(SUM(inv.qty),0) AS on_hand
  FROM inventory_item i
  LEFT JOIN inventory_inventory inv ON inv.item_id = i.id
  LEFT JOIN inventory_bin b ON b.id = inv.bin_id
  LEFT JOIN inventory_location l ON l.id = b.location_id
  GROUP BY i.id, l.id
)
SELECT i.sku, l.code AS location, COALESCE(s.on_hand,0) AS on_hand, rp.reorder_point, rp.reorder_qty
FROM inventory_reorderpolicy rp
JOIN inventory_item i ON i.id = rp.item_id
LEFT JOIN inventory_location l ON l.id = rp.location_id
LEFT JOIN stock s ON s.item_id = rp.item_id AND s.location_id = rp.location_id
WHERE COALESCE(s.on_hand,0) < rp.reorder_point
ORDER BY i.sku, l.code
""")

vn.train(
    question="Reorder-Vorschläge für MAIN (unter RP, mit Bestellmenge)",
    sql="""
WITH stock AS (
  SELECT i.id AS item_id, l.id AS location_id, COALESCE(SUM(inv.qty),0) AS on_hand
  FROM inventory_item i
  LEFT JOIN inventory_inventory inv ON inv.item_id = i.id
  LEFT JOIN inventory_bin b ON b.id = inv.bin_id
  LEFT JOIN inventory_location l ON l.id = b.location_id
  GROUP BY i.id, l.id
)
SELECT i.sku, l.code AS location, COALESCE(s.on_hand,0) AS on_hand, 
       rp.reorder_point, rp.reorder_qty,
       GREATEST(rp.reorder_qty, rp.reorder_point - COALESCE(s.on_hand,0)) AS suggested_qty
FROM inventory_reorderpolicy rp
JOIN inventory_item i ON i.id = rp.item_id
LEFT JOIN inventory_location l ON l.id = rp.location_id
LEFT JOIN stock s ON s.item_id = rp.item_id AND s.location_id = rp.location_id
WHERE l.code = 'MAIN' AND COALESCE(s.on_hand,0) < rp.reorder_point
ORDER BY i.sku
""")

# ---- 2d) Bewegungen / Analytics ----
vn.train(
    question="Letzte 50 Bewegungen gesamt (SKU, von/nach, ts, qty)",
    sql=f"""
SELECT sl.ts, i.sku,
       fb.code AS from_bin, tb.code AS to_bin,
       sl.qty, sl.ref_type, sl.ref_id
FROM inventory_stockledger sl
JOIN inventory_item i ON i.id = sl.item_id
LEFT JOIN inventory_bin fb ON fb.id = sl.from_bin_id
LEFT JOIN inventory_bin tb ON tb.id = sl.to_bin_id
ORDER BY sl.ts DESC
{limit_clause(50)}
""")

vn.train(
    question="Top 5 Artikel nach Bewegungsmenge in den letzten 30 Tagen",
    sql="""
SELECT i.sku, COALESCE(SUM(ABS(sl.qty)),0) AS moved_qty
FROM inventory_stockledger sl
JOIN inventory_item i ON i.id = sl.item_id
WHERE sl.ts >= NOW() - INTERVAL '30 days'
GROUP BY i.sku
ORDER BY moved_qty DESC
LIMIT 5
""")

# ---- 3) (Optional) Beispiele mit echten SKUs/Bins aus DB ergänzen ----
print(">>> 3) Optional: echte SKUs/Bins aus DB als Trainingsvariation")
try:
    df_skus = vn.run_sql("SELECT sku FROM inventory_item ORDER BY sku " + limit_clause(5))
    real_skus = [r["sku"] for r in df_skus.to_dict(orient="records")]
    for sku in real_skus:
        vn.train(
            question=f"Bestand je Bin für SKU {sku}",
            sql=f"""
SELECT b.code AS bin, l.code AS location, inv.qty
FROM inventory_item i
JOIN inventory_inventory inv ON inv.item_id = i.id
JOIN inventory_bin b ON b.id = inv.bin_id
JOIN inventory_location l ON l.id = b.location_id
WHERE i.sku = '{sku}'
ORDER BY l.code, b.code
""")
except Exception as e:
    print("Hinweis: Konnte echte SKUs nicht lesen (ok im leeren System):", e)

print("Training fertig.")
