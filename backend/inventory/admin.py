from django.contrib import admin
from .models import Item, ItemAlias, Location, Bin, ReorderPolicy, StockLedger, Inventory

class ItemAliasInline(admin.TabularInline):
    model = ItemAlias
    extra = 1

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "uom", "active")
    search_fields = ("sku", "name", "aliases__alias")
    inlines = [ItemAliasInline]

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")

@admin.register(Bin)
class BinAdmin(admin.ModelAdmin):
    list_display = ("code", "location")
    list_filter = ("location",)
    search_fields = ("code", "location__code")

@admin.register(ReorderPolicy)
class ReorderPolicyAdmin(admin.ModelAdmin):
    list_display = ("item", "location", "min_qty", "reorder_point", "reorder_qty")
    list_filter = ("location", "item")

@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = ("ts", "item", "qty", "from_bin", "to_bin", "ref_type", "ref_id")
    list_filter = ("ref_type", "item")

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("item", "bin", "qty")
    list_filter = ("bin__location", "item")