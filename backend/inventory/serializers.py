from rest_framework import serializers
from .models import Item, Location, Bin, ReorderPolicy, StockLedger, Inventory

class InventoryBinSerializer(serializers.Serializer):
    bin = serializers.CharField()
    location = serializers.CharField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=3)

class StockResponseSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    on_hand = serializers.DecimalField(max_digits=18, decimal_places=3)
    bins = InventoryBinSerializer(many=True)

from rest_framework import serializers
from .models import Item, Location, Bin, ReorderPolicy, StockLedger, Inventory

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = "__all__"

class BinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bin
        fields = "__all__"

class ReorderPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReorderPolicy
        fields = "__all__"

class StockLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLedger
        fields = "__all__"
        read_only_fields = ("ts",)

class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = "__all__"
