# from django.core.cache import cache
# from django.db.models import F
# from app.product.models import Product

# class InventoryCache:
#     P, S = "inv_{}", "stop_{}"
#     _k = lambda cls, p, t: t.format(p)
    
#     @classmethod
#     def reserve_cart(cls, user):
#         from app.cart.models import Cart
#         items = Cart.objects.filter(user=user).select_related('products_id')
#         if not items.exists():
#             return False, "empty", "السلة فارغة", []
        
#         allocations = []
#         for item in items:
#             pid, qty = item.products_id.id, item.quantity
            
#             if cache.get(cls._k(pid, cls.S)):
#                 for a in allocations: cls.release(a['pid'], a['qty'])
#                 return False, "depleted", f"نفد المنتج {item.products_id.name} بالكامل", []
            
#             r = cache.get(cls._k(pid, cls.P), 0)
#             try:
#                 stock = Product.objects.values_list('stock', flat=True).get(id=pid)
#             except Product.DoesNotExist:
#                 for a in allocations: cls.release(a['pid'], a['qty'])
#                 return False, "notfound", "المنتج غير موجود", []
            
#             if r + qty > stock:
#                 for a in allocations: cls.release(a['pid'], a['qty'])
#                 if stock == 0:
#                     return False, "depleted", f"نفد المنتج {item.products_id.name} بالكامل", []
#                 return False, "insufficient", f"لا يوجد كمية كافية (المتبقي: {stock - r})", []
            
#             cache.set(cls._k(pid, cls.P), r + qty, 300)
#             allocations.append({'pid': pid, 'qty': qty})
        
#         return True, "ok", "تم الحجز", allocations
    
#     @classmethod
#     def commit(cls, pid, qty):
#         r = cache.get(cls._k(pid, cls.P), 0)
#         new_r = max(0, r - qty)
#         if new_r == 0:
#             cache.delete(cls._k(pid, cls.P))
#             cache.set(cls._k(pid, cls.S), True, 3600)
#         else:
#             cache.set(cls._k(pid, cls.P), new_r, 300)
#         Product.objects.filter(id=pid).update(stock=F('stock') - qty)
    
#     @classmethod
#     def release(cls, pid, qty):
#         r = cache.get(cls._k(pid, cls.P), 0)
#         new_r = max(0, r - qty)
#         cache.set(cls._k(pid, cls.P), new_r, 300) if new_r else cache.delete(cls._k(pid, cls.P))