from django.contrib import admin
from .models import Item, Location, Bin, ReorderPolicy, StockLedger, Inventory

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("sku","name","uom","active")
    search_fields = ("sku","name")

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code","name")

@admin.register(Bin)
class BinAdmin(admin.ModelAdmin):
    list_display = ("location","code")
    list_filter = ("location",)

@admin.register(ReorderPolicy)
class ReorderPolicyAdmin(admin.ModelAdmin):
    list_display = ("item","location","min_qty","reorder_point","reorder_qty")
    list_filter = ("location",)

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("item","bin","qty")
    list_filter = ("bin__location",)

@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = ("ts","item","from_bin","to_bin","qty","ref_type","ref_id")
    list_filter = ("ref_type","item")
    date_hierarchy = "ts"

