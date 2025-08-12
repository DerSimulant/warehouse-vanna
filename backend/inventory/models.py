from django.db import models

class Item(models.Model):
    sku = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    uom = models.CharField(max_length=20, default='pcs')
    active = models.BooleanField(default=True)
    def __str__(self): return f"{self.sku} - {self.name}"

class Location(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100, blank=True)
    def __str__(self): return self.code

class Bin(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    code = models.CharField(max_length=50)
    class Meta:
        unique_together = (('location','code'),)
    def __str__(self): return f"{self.location.code}-{self.code}"

class ReorderPolicy(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)
    min_qty = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    reorder_point = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    reorder_qty = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    class Meta:
        unique_together = (('item','location'),)

class StockLedger(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    from_bin = models.ForeignKey("Bin", on_delete=models.SET_NULL, null=True, blank=True, related_name='out_ledger')
    to_bin = models.ForeignKey("Bin", on_delete=models.SET_NULL, null=True, blank=True, related_name='in_ledger')
    qty = models.DecimalField(max_digits=18, decimal_places=3)
    ref_type = models.CharField(max_length=50, blank=True)
    ref_id = models.CharField(max_length=100, blank=True)

class Inventory(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE)
    qty = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    class Meta:
        unique_together = (('item','bin'),)


# Create your models here.
