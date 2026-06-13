from django.contrib import admin, messages

from app.product.catalog_cache import evict_product
from app.product.inventory import adjust_stock
from app.product.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'stock', 'version')
    actions = ('restock_plus_ten',)

    @admin.action(description='Restock +10 (optimistic locking path)')
    def restock_plus_ten(self, request, queryset):
        for product in queryset:
            try:
                adjust_stock(product.id, 10)
            except Exception as exc:
                self.message_user(request, f'{product.name}: {exc}', level=messages.ERROR)
                continue
            self.message_user(request, f'Restocked {product.name} by 10')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        evict_product(obj.pk)
