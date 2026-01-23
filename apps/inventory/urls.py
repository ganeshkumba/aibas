from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('business/<int:business_id>/', views.inventory_dashboard, name='dashboard'),
]
