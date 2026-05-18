from celery import shared_task
from django.db import transaction, DatabaseError
from django.db.models import F
from app.cart.models import Cart
from app.product.models import Product
from .models import Invoice
from celery import shared_task
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField
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
    # include any invoice that is not pending (project uses 'pending' as initial state)
    invoices = Invoice.objects.exclude(status='pending').filter(
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
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

    # If no invoices found, fallback to aggregating from Cart (estimate)
    if not invoices.exists():
        carts = Cart.objects.filter(
            created_at__date__gte=week_start,
            created_at__date__lte=week_end,
        )
        cart_agg = carts.aggregate(
            total=Sum(ExpressionWrapper(F('quantity') * F('products_id__price'), output_field=DecimalField(max_digits=15, decimal_places=2))),
            count=Count('id'),
            total_items=Sum('quantity')
        )
        sales_total = cart_agg['total'] or 0
        orders_count = cart_agg['count'] or 0
        items_total = cart_agg['total_items'] or 0
        top_cart = carts.values('products_id__name').annotate(sold=Sum('quantity')).order_by('-sold').first()
        top_name = top_cart['products_id__name'] if top_cart else ''

        report, _ = WeeklyReport.objects.update_or_create(
            week_start=week_start,
            week_end=week_end,
            defaults={
                'total_sales': sales_total,
                'total_orders': orders_count,
                'total_items_sold': items_total,
                'avg_order_value': (sales_total / orders_count) if orders_count else 0,
                'top_product': top_name,
            }
        )
    else:
        # حفظ التقرير من الفواتير الفعلية
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


@shared_task
def generate_report_range(start_date: str = None, end_date: str = None):
    """Generate report for a given date range. Dates must be ISO 'YYYY-MM-DD' strings.
    If `start_date` is None, use the earliest Invoice.created_at date. If `end_date` is None, use today.
    """
    # parse dates if provided
    from django.utils.dateparse import parse_date

    if start_date:
        start = parse_date(start_date)
    else:
        first = Invoice.objects.order_by('created_at').first()
        start = first.created_at.date() if first else timezone.now().date()

    if end_date:
        end = parse_date(end_date)
    else:
        end = timezone.now().date()

    # include any invoice that is not pending to capture completed/delivered records
    invoices = Invoice.objects.exclude(status='pending').filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
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

    top = InvoiceItem.objects.filter(
        invoice__in=invoices
    ).values('product_name').annotate(
        sold=Sum('quantity')
    ).order_by('-sold').first()

    if not invoices.exists():
        carts = Cart.objects.filter(
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        cart_agg = carts.aggregate(
            total=Sum(ExpressionWrapper(F('quantity') * F('products_id__price'), output_field=DecimalField(max_digits=15, decimal_places=2))),
            count=Count('id'),
            total_items=Sum('quantity')
        )
        sales_total = cart_agg['total'] or 0
        orders_count = cart_agg['count'] or 0
        items_total = cart_agg['total_items'] or 0
        top_cart = carts.values('products_id__name').annotate(sold=Sum('quantity')).order_by('-sold').first()
        top_name = top_cart['products_id__name'] if top_cart else ''

        report, _ = WeeklyReport.objects.update_or_create(
            week_start=start,
            week_end=end,
            defaults={
                'total_sales': sales_total,
                'total_orders': orders_count,
                'total_items_sold': items_total,
                'avg_order_value': (sales_total / orders_count) if orders_count else 0,
                'top_product': top_name,
            }
        )
    else:
        report, _ = WeeklyReport.objects.update_or_create(
            week_start=start,
            week_end=end,
            defaults={
                'total_sales': sales['total'] or 0,
                'total_orders': sales['count'] or 0,
                'total_items_sold': items['total_items'] or 0,
                'avg_order_value': (sales['total'] / sales['count']) if sales['count'] else 0,
                'top_product': top['product_name'] if top else '',
            }
        )

    return f"Report {report.id}: ${report.total_sales}"