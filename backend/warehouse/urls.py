# warehouse/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from rest_framework.routers import DefaultRouter
from inventory.views import (
    ItemViewSet, LocationViewSet, BinViewSet,
    ReorderPolicyViewSet, StockLedgerViewSet, InventoryViewSet,
    health, stock, reorder_suggestions, receive_goods, move_goods,
    stock_moves, issue_goods, resolve_item
)


from inventory.views import resolve_item  # ✅ richtige View importieren
# NICHT: from inventory.views import resolve_bin as resolve_item


router = DefaultRouter()
router.register(r"items", ItemViewSet)
router.register(r"locations", LocationViewSet)
router.register(r"bins", BinViewSet)
router.register(r"reorder-policies", ReorderPolicyViewSet)
router.register(r"ledger", StockLedgerViewSet, basename="ledger")
router.register(r"inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("admin/", admin.site.urls),

    # DRF Router (CRUD)
    path("api/", include(router.urls)),

    # Auth
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
   

    # Funktionsendpunkte – ALLE unter /api/ und mit trailing slash
    path("api/health/", health, name="health"),
     # GET-Endpoints
     # GET-Endpoints
    path("api/stock/", stock),
    path("api/stock-moves/", stock_moves),
    path("api/resolve-item/", resolve_item),
    path("api/reorder/suggestions/", reorder_suggestions),

    # POST-Endpoints
    path("api/stock/receive/", receive_goods),
    path("api/stock/move/", move_goods),
    path("api/stock/issue/", issue_goods),
]
