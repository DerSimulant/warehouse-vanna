"""
URL configuration for warehouse project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter
from inventory.views import (
    ItemViewSet, LocationViewSet, BinViewSet,
    ReorderPolicyViewSet, StockLedgerViewSet, InventoryViewSet,
    health, stock, reorder_suggestions, receive_goods, move_goods
)

router = DefaultRouter()
router.register(r"items", ItemViewSet)
router.register(r"locations", LocationViewSet)
router.register(r"bins", BinViewSet)
router.register(r"reorder-policies", ReorderPolicyViewSet)
router.register(r"ledger", StockLedgerViewSet, basename="ledger")
router.register(r"inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/token", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    # die drei Funktions-Endpoints von vorhin:
    path("api/health", health),
    path("api/stock", stock),
    path("api/reorder/suggestions", reorder_suggestions),
    path("api/stock/receive", receive_goods),
    path("api/stock/move", move_goods),
]
