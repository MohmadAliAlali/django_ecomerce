from celery import shared_task
from django.core.exceptions import ValidationError
from app.cart.models import Cart
from app.wallets.models import Wallet
from app.product.models import Product
from .models import Invoice, InvoiceItem
from django.db.models import F, Sum
from django.db import transaction
import time

@shared_task(bind=True, max_retries=3)
def process_purchase_order_task(self, user_id):

    from django.contrib.auth.models import User
    user = User.objects.get(id=user_id)
    
    # جلب السلة
    cart_items = Cart.objects.filter(user=user)
    if not cart_items.exists():
        return {"status": "failed", "reason": "Cart Empty"}

    # حساب المبلغ
    total_amount = sum(item.total_price() for item in cart_items)

    try:
        with transaction.atomic():
            # خصم الرصيد (للحجز المكان)
            wallet = user.wallet
            wallet.balance -= total_amount
            wallet.save()

            # إنشاء الفاتورة
            invoice = Invoice.objects.create(
                user=user,
                total_amount=total_amount,
                status='completed' # نجح الشراء
            )

            # معالجة المنتجات
            for item in cart_items:
                product = item.products_id
                
                # --- المعادلة الذكية (Atomic Update) ---
                # نقوم بتحديث الرصيد بـ F()
                # إذا نفد، سيرمي قاعدة البيانات شرطاً خاطئاً وسنتعامل معه
                updated_rows = Product.objects.filter(
                    pk=product.pk,
                    stock__gte=item.quantity # الشرط: مخزون >= كمية
                ).update(
                    stock=F('stock') - item.quantity
                )
                
                if updated_rows == 0:
                    # نفد المخزون!
                    # نقوم بإلغاء الفاتورة وإعادة الرصيد
                    raise ValidationError(f"Product {product.name} out of stock.")
                
                # إذا نجح، نضيف للفاتورة
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product_name=item.products_id.name,
                    quantity=item.quantity,
                    price=item.products_id.price
                )

            # تفريغ السلة
            cart_items.delete()
            
        return {"status": "success", "invoice_id": invoice.id}

    except ValidationError as e:
        # --- المرحلة 2: المخزون نفد (وضع الانتظار) ---
        print(f"⚠️ المخزون نفد للمستخدم {user.username}: {e}")
        
        # خيار أ: إرجاع الرصيد وترك السلة كما هي (انتظار صامت)
        # بهذه الطريقة، عندما يعاد تشغيل الـ Task مرة أخرى، سيجد السلة كاملة
        # وسيحاول الشراء مرة أخرى.
        wallet = user.wallet
        wallet.balance += total_amount
        wallet.save()
        
        # إعادة جدولة المهمة مرة أخرى بعد 10 ثوانٍ
        raise self.retry(exc=e, countdown=10)

    except Exception as e:
        return {"status": "failed", "reason": str(e)}