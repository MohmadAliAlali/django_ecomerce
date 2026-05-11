from django.urls import path
from .views import CartCreateView, CartDetailView, CartDeleteView

urlpatterns = [
    # إنشاء سلة (POST)
    path('create/', CartCreateView.as_view(), name='cart-create'),
    
    # عرض السلة (GET) - سنستخدم الـ id الخاص بالمستخدم كمثال، أو يمكننا تركها تعتمد على الكود
    path('my-cart/', CartDetailView.as_view(), name='cart-detail'),
    
    # حذف السلة (DELETE)
    path('my-cart/delete/', CartDeleteView.as_view(), name='cart-delete'),
]