from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user
    

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("البيانات غير صحيحة.")
        else:
            raise serializers.ValidationError("يجب إدخال اسم المستخدم وكلمة المرور.")

        # نمرر المستخدم بعد التحقق منه ليكون متاحاً في الـ View
        data['user'] = user
        return data