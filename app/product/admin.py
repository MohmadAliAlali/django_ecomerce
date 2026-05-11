from django.contrib import admin
# Register your models here.
from .models import Product  # Import your model

admin.site.register(Product)