from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'stock']

    def validate_stock(self, value):
        """دالة للتحقق من أن الكمية موجودة (تسمى validate_stock)"""
        if value < 0:
            raise serializers.ValidationError("الكمية في المخزون لا يمكن أن تكون سلبية.")
        return value

    def to_representation(self, instance):
        """
        هذه الدالة يتم استدعاؤها عند تحويل الموديل إلى JSON.
        يمكننا هنا منع عرض المنتج إذا كان مخزونه 0
        """
        # إذا المخزون 0 أو أقل، نعيد قاموس فارغ (لن يتم عرضه في الرد)
        if instance.stock <= 0:
            return {} 
        return super().to_representation(instance)
    
class ProductItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields  = ['id', 'name', 'description', 'price', 'stock']