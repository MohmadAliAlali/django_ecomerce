from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'stock']
    def validateStock(self, value):
        if value < 0:
            raise serializers.ValidationError("الكمية في المخزون لا يمكن أن تكون سلبية.")
        return value



    