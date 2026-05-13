from rest_framework import serializers
from .models import Cart

class CartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        # أضفنا products_id و quantity هنا ليتمكن السيرياليزر من استقبال البيانات وحفظها
        fields = ['id', 'user', 'products_id', 'quantity', 'created_at'] 
        read_only_fields = ['id', 'user', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        # if products_id := validated_data.get('products_id'):
        #     if not products_id.exists():
        #         raise serializers.ValidationError("المنتج غير موجود.")
        validated_data['user'] = request.user
        return super().create(validated_data)