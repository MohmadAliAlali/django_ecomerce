from rest_framework import serializers
from .models import Cart

class CartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = ['id', 'created_at'] 
        read_only_fields = ['id', 'user', 'created_at']

    def validate(self, attrs):
        """
        1. التحقق من عدم وجود سلة مسبقاً (Logic تم نقله من الـ View)
        يتم استدعاؤها قبل الحفظ
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # التحقق من وجود سلة للمستخدم
            if Cart.objects.filter(user=request.user).exists():
                raise serializers.ValidationError("لديك سلة بالفعل، لا يمكن إنشاء سلة جديدة.")
        return attrs

    def create(self, validated_data):
        """
        2. ربط المستخدم (Logic تم نقله من الـ View)
        يتم استدعاؤها عند التحقق النهائي والحفظ
        """
        request = self.context.get('request')
        
        # إضافة المستخدم إلى البيانات المراد حفظها
        validated_data['user'] = request.user
        
        # استدعاء دالة الحفظ الأصلية للـ Model
        return super().create(validated_data)