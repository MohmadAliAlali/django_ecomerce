import random
from celery import shared_task
from django.core.exceptions import ValidationError
from app.cart.models import Cart
from app.wallets.models import Wallet
from app.product.models import Product
from .models import Invoice, InvoiceItem
from django.db.models import F, Sum
from django.db import transaction

@shared_task(bind=True, max_retries=5) # الحد الأقصى للمحاولات (السيناريو الحالي + الانتظار)
def process_purchase_order_task(self, user_id):
    from django.contrib.auth.models import User
    user = User.objects.get(id=user_id)
    
    # جلب السلة
    cart_items = Cart.objects.filter(user=user).order_by('products_id')
    
    if not cart_items.exists():
        return {"status": "failed", "reason": "Cart Empty"}

    total_amount = sum(item.total_price() for item in cart_items)

    try:
        with transaction.atomic():
            # 1. خصم الرصيد (حجز المكان)
            wallet = user.wallet
            wallet.balance -= total_amount
            wallet.save()

            invoice = Invoice.objects.create(
                user=user,
                total_amount=total_amount,
                status='completed'
            )

            # 2. محاولة حجز المخزون
            for item in cart_items:
                product = item.products_id
                
                updated_rows = Product.objects.filter(
                    pk=product.pk,
                    stock__gte=item.quantity
                ).update(
                    stock=F('stock') - item.quantity
                )
                
                if updated_rows == 0:
                    # المخزون نفد، نعيد المال ونلغي الفاتورة
                    raise ValidationError(f"Product {product.name} out of stock.")
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product_name=item.products_id.name,
                    quantity=item.quantity,
                    price=item.products_id.price
                )

            # 3. نجاح: تفريغ السلة
            cart_items.delete()
            
        return {"status": "success", "invoice_id": invoice.id}

    except ValidationError as e:
        # --- منطق إعادة المحاولة (Retry) ---
        print(f"⏳ المحاولة {self.request.retries}/5: المخزون نفد للمستخدم {user.username}")
        
        # إرجاع المال الذي تم خصمه (لأنه لم يتم الشراء)
        wallet = user.wallet
        wallet.balance += total_amount
        wallet.save()
        
        # التحقق: هل وصلنا لحد المحاولات القصوى؟
        # max_retries في الديكور هو 5، ونحن الآن في المحاولة رقم ...
        # إذا كانت المحاولات المتبقية أكبر من 0، نعيد المحاولة
        if self.request.retries < self.max_retries:
            # انتظار عشوائي لتفادي السحب (Deadlock) بين المحاولات
            retry_delay = random.randint(3, 7)
            raise self.retry(exc=e, countdown=retry_delay)
        
        else:
            # --- استراتيجية الانسحاب (Give Up Strategy) ---
            # وصلنا للحد الأقصى (5 محاولات) ولا يزال المنتج غير متوفر.
            # هذا يعني أن هناك "طابور انتظار" طويل جداً ونفدت الفرص.
            
            print(f"❌ فشل نهائي للمستخدم {user.username} بعد 5 محاولات. المخزون نفد نهائياً.")
            
            # 1. تفريغ السلة (حذف المنتجات غير المتاحة)
            cart_items.delete()
            
            # 2. إرجاع المال (للتأكيد)
            # (تم بالأعلى، لكن للتأكد)
            wallet.balance += total_amount
            wallet.save()
            
            # 3. هنا يمكنك إرسال إشعار (Notification)
            # مثلاً: Notification.objects.create(user=user, message="نعتذر عن عدم توفر المنتج.")
            
            return {
                "status": "failed", 
                "reason": "عذراً، نفدت الكمية تماماً ونعتذر عن عدم إتمام طلبك.",
                "retry_limit_reached": True
            }

    except Exception as e:
        # أي خطأ آخر غير معروف (مشكلة تقنية)
        print(f"⚠️ خطأ تقني: {e}")
        # إرجاع المال
        wallet = user.wallet
        wallet.balance += total_amount
        wallet.save()
        
        return {"status": "failed", "reason": str(e)}