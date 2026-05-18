from celery import shared_task
from django.db import transaction, DatabaseError
from django.db.models import F
from app.cart.models import Cart
from app.product.models import Product
from .models import Invoice
from celery import shared_task
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from .models import Invoice, InvoiceItem, WeeklyReport

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




@shared_task
def generate_weekly_report():
    """تقرير أسبوعي - يعمل كل أحد الساعة 2 صباحاً"""
    today = timezone.now().date()
    week_end = today - timedelta(days=today.weekday() + 1)  # آخر سبت
    week_start = week_end - timedelta(days=6)  # الأحد الماضي

    # جمع البيانات
    invoices = Invoice.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
        status='completed'
    )

    sales = invoices.aggregate(
        total=Sum('total_amount'),
        count=Count('id')
    )

    items = InvoiceItem.objects.filter(
        invoice__in=invoices
    ).aggregate(
        total_items=Sum('quantity')
    )

    # المنتج الأكثر مبيعاً
    top = InvoiceItem.objects.filter(
        invoice__in=invoices
    ).values('product_name').annotate(
        sold=Sum('quantity')
    ).order_by('-sold').first()

    # حفظ التقرير
    report, _ = WeeklyReport.objects.update_or_create(
        week_start=week_start,
        week_end=week_end,
        defaults={
            'total_sales': sales['total'] or 0,
            'total_orders': sales['count'] or 0,
            'total_items_sold': items['total_items'] or 0,
            'avg_order_value': (sales['total'] / sales['count']) if sales['count'] else 0,
            'top_product': top['product_name'] if top else '',
        }
    )

    return f"Report {report.id}: ${report.total_sales}"