from django.db import models
from  django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
# Create your models here.
class Cart(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    products_id = models.ForeignKey('product.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1 , validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart of {self.user.username} created on {self.created_at}"
    def total_price(self):
        return self.quantity * self.products_id.price
    def save(self, *args, **kwargs):
        if self.quantity <= 0:
            raise ValueError("Can't add product with zero or negative quantity.")
        super().save(*args, **kwargs)
    def clean(self):
        # تصحيح الخطأ: self.product -> self.products_id
        # التأكد من أن products_id موجود قبل التحقق من المخزون
        if self.products_id and self.quantity > self.products_id.stock:
            raise ValidationError(
                f"نأسف، الكمية المطلوبة غير متوفرة. المتوفر فقط: {self.products_id.stock}"
            )
