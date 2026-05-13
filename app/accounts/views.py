from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from .serializers import SignupSerializer , LoginSerializer

class SignupCreateAPIView(CreateAPIView):
    """
    دالة التسجيل الجديدة، تعمل بدون ViewModel وتولد توكن مباشرة
    """
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]  # <--- 2. السماح للجميع بالوصول لهذه الصفحة

    def create(self, request, *args, **kwargs):
        # 1. التحقق من البيانات باستخدام السيريالايزر
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. حفظ المستخدم (هذه الخطوة تشفر الباسوورد أيضاً)
        user = serializer.save()

        # 3. توليد أو استرجاع التوكن الخاص بهذا المستخدم
        token, created = Token.objects.get_or_create(user=user)

        # 4. إرجاع البيانات مع التوكن
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'token': token.key
        }, status=status.HTTP_201_CREATED)
    


class LoginView(CreateAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # استخراج المستخدم من الـ Serializer بعد التحقق
        user = serializer.validated_data['user']
        
        # إنشاء أو جلب التوكن
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            "message": "تم تسجيل الدخول بنجاح",
            "token": token.key,
            "username": user.username
        }, status=status.HTTP_200_OK)