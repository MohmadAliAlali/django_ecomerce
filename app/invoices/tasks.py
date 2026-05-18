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



