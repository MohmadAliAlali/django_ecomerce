from celery import shared_task
from django.db import transaction, DatabaseError
from django.db.models import F
from app.cart.models import Cart
from app.product.models import Product
from .models import Invoice

class OrderProcessingError(Exception):
    pass

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_purchase_order_task(self, user_id):
    try:
        with transaction.atomic():
            
            cart_items = Cart.objects.select_related('products_id').filter(user_id=user_id)
            
            if not cart_items.exists():
                raise OrderProcessingError("Cart is empty")

            total_price = 0

            for item in cart_items:
                
                product = item.products_id
                
                updated_rows = Product.objects.filter(
                    id=product.id, 
                    stock__gte=item.quantity
                ).update(stock=F('stock') - item.quantity)

                if updated_rows == 0:
                    raise OrderProcessingError(f"{product.name} is out of stock")

                total_price += (product.price * item.quantity)

            invoice = Invoice.objects.create(
                user_id=user_id,
                total_amount=total_price
            )

            cart_items.delete()

            return {
                "status": "success",
                "message": "Order processed successfully",
                "invoice_id": invoice.id
            }

    except OrderProcessingError as e:
        return {
            "status": "failed",
            "error": str(e)
        }

    except DatabaseError as e:
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "error": "Max retries exceeded for database error"}
            
    except Exception as e:
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "error": "Unexpected error occurred"}











#---------------------------------------------
# from django.contrib.auth.models import User
# from django.db import transaction
# from django_q.tasks import async_task
# from .cache import InventoryCache
# from .models import Invoice, InvoiceItem
# from app.cart.models import Cart
# from app.wallets.models import Wallet
# from app.product.models import Product

# from django.contrib.auth.models import User
# from django.db import transaction
# from django.utils import timezone
# from datetime import timedelta
# from django_q.models import Schedule
# from .cache import InventoryCache
# from .models import Invoice, InvoiceItem
# from app.cart.models import Cart
# from app.wallets.models import Wallet

# def process_or_wait(user_id, attempt=1):
#     from django.utils import timezone
#     from datetime import timedelta
#     from django_q.models import Schedule
    
#     user = User.objects.get(id=user_id)
    
#     ok, msg, allocations = InventoryCache.reserve_cart(user)
#     if ok:
#         async_task(
#             'app.invoices.tasks.process_order',
#             user_id,
#             hook='app.invoices.hooks.on_done'
#         )
#         return {"status": "processing", "items": len(allocations)}
    
#     if attempt >= 3:
#         return {"status": "failed", "reason": msg}
    
#     Schedule.objects.create(
#         func='app.invoices.tasks.process_or_wait',
#         args=(user_id, attempt + 1),
#         schedule_type=Schedule.ONCE,
#         next_run=timezone.now() + timedelta(seconds=30),
#     )
#     return {"status": "waiting", "attempt": attempt, "retry_in": 30, "reason": msg}

# def process_order(user_id):
#     user = User.objects.get(id=user_id)
#     items = Cart.objects.filter(user=user).select_related('products_id')
    
#     total = sum(i.total_price() for i in items)
    
#     with transaction.atomic():
#         wallet = user.wallet
#         if wallet.balance < total:
#             raise Exception("رصيد غير كافٍ")
        
#         wallet.balance -= total
#         wallet.save()
        
#         inv = Invoice.objects.create(user=user, total_amount=total, status='completed')
        
#         for item in items:
#             pid = item.products_id.id
#             qty = item.quantity
            
#             InventoryCache.commit(pid, qty)
            
#             InvoiceItem.objects.create(
#                 invoice=inv,
#                 product_name=item.products_id.name,
#                 quantity=qty,
#                 price=item.products_id.price
#             )
        
#         items.delete()
    
#     return {"status": "success", "invoice_id": inv.id}


# def process_order_sync(user_id):
#     """تنفيذ فوري (Synchronous) — يُنفذ في الـ View مباشرة"""
#     user = User.objects.get(id=user_id)
#     items = Cart.objects.filter(user=user).select_related('products_id')
#     total = sum(i.total_price() for i in items)
    
#     with transaction.atomic():
#         wallet = user.wallet
#         if wallet.balance < total:
#             raise Exception("رصيد غير كافٍ")
        
#         wallet.balance -= total
#         wallet.save()
        
#         inv = Invoice.objects.create(user=user, total_amount=total, status='completed')
        
#         for item in items:
#             pid, qty = item.products_id.id, item.quantity
#             InventoryCache.commit(pid, qty)
#             InvoiceItem.objects.create(
#                 invoice=inv,
#                 product_name=item.products_id.name,
#                 quantity=qty,
#                 price=item.products_id.price
#             )
        
#         items.delete()
    
#     return {"status": "success", "invoice_id": inv.id}

# def attempt_process(user_id, attempt=1):
#     """محاولة من الطابور — تُنفذها Django-Q2 Scheduler"""
#     user = User.objects.get(id=user_id)
#     ok, code, msg, allocations = InventoryCache.reserve_cart(user)
    
#     if ok:
#         try:
#             return process_order_sync(user_id)
#         except Exception:
#             for a in allocations:
#                 InventoryCache.release(a['pid'], a['qty'])
#             if attempt < 3:
#                 _schedule(user_id, attempt + 1)
#             return {"status": "failed", "reason": "فشل التنفيذ"}
    
#     if code == "insufficient" and attempt < 3:
#         _schedule(user_id, attempt + 1)
#         return {"status": "waiting", "attempt": attempt}
    
#     return {"status": "failed", "reason": msg}

# def _schedule(user_id, attempt):
#     Schedule.objects.create(
#         func='app.invoices.tasks.attempt_process',
#         args=(user_id, attempt),
#         schedule_type=Schedule.ONCE,
#         next_run=timezone.now() + timedelta(seconds=30),
#     )