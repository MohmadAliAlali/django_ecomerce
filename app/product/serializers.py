from rest_framework import serializers

class ProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField()
    price = serializers.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    stock = serializers.IntegerField()
    created_at = serializers.DateTimeField(read_only=True)

    def validateStock(self, value):
        if value < 0:
            raise serializers.ValidationError("الكمية في المخزون لا يمكن أن تكون سلبية.")
        return value



    