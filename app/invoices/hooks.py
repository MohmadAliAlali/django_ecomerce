# from .cache import InventoryCache
# from app.cart.models import Cart
# from app.wallets.models import Wallet
# from django.contrib.auth.models import User

# def on_done(task):
#     if not task.success:
#         user_id = task.args[0]
#         user = User.objects.get(id=user_id)
        
#         # إرجاع كل الحجوزات للذاكرة
#         items = Cart.objects.filter(user=user).select_related('products_id')
#         for item in items:
#             InventoryCache.release(item.products_id.id, item.quantity)
        
#         # إرجاع المال إذا خُصم
#         try:
#             w = user.wallet
#             # نحتاج معرفة المبلغ — يمكن تخزينه مؤقتاً
#         except Exception:
#             pass