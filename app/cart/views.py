from rest_framework.generics import ListAPIView, CreateAPIView, DestroyAPIView
from rest_framework.permissions import IsAuthenticated
from .serializers import CartSerializer
from .models import Cart

class CartCreateView(CreateAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

# استخدام ListAPIView بدلاً من RetrieveAPIView لعرض جميع منتجات السلة
class CartDetailView(ListAPIView): 
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # إرجاع جميع السجلات المرتبطة بهذا المستخدم
        return Cart.objects.filter(user=self.request.user)

# ملاحظة: CartDeleteView الحالي سيحذف كل سلة المستخدم دفعة واحدة.
# إذا كنت تريد حذف منتج معين، ستحتاج لتعديلها لاستقبال id المنتج.
class CartDeleteView(DestroyAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    
    # كن حذراً، هذا سيحاول حذف السلة بالكامل بناءً على المستخدم
    # إذا كان هناك عدة منتجات، سيرمي خطأ MultipleObjectsReturned
    def get_object(self):
        return Cart.objects.filter(user=self.request.user).first() 