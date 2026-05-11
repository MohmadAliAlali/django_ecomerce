# viewmodels/base_viewmodel.py
import logging
from django.db import IntegrityError
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class BaseViewModel:

    serializer_class = None

    def __init__(self, data, context=None):
        if not self.serializer_class:
            raise ValueError("يجب تحديد serializer_class في الفئة الفرعية")
        
        self.data = data
        self.context = context or {}
        # تهيئة السيريلايزر
        self.serializer = self.serializer_class(data=data, context=self.context)

    def is_valid(self):
        """التحقق من صحة البيانات"""
        return self.serializer.is_valid()

    def errors(self):
        """إرجاع أخطاء التحقق"""
        return self.serializer.errors

    def perform_action(self):
        """
        هذه الدالة هي التي سيتم تجاوزها (Override) في الفئات الفرعية.
        هنا تتم كتابة منطق الحفظ في قاعدة البيانات.
        """
        raise NotImplementedError("يجب تنفيذ دالة perform_action في الفئة الفرعية")

    def execute(self):
        """
        المنفذ الرئيسي الآمن.
        يقوم بتغليف العملية بـ try/except لضمان عدم تعطل التطبيق.
        """
        # 1. التحقق من صحة البيانات أولاً
        if not self.is_valid():
            return {
                'success': False,
                'data': self.errors(),
                'status': 400
            }

        try:
            # 2. تنفيذ العملية (الحفظ، التعديل، الحذف...)
            result_data = self.perform_action()
            
            # 3. إرجاع النجاح
            return {
                'success': True,
                'data': result_data or {'message': 'تمت العملية بنجاح'},
                'status': 201
            }

        except ValidationError as e:
            # خطأ في التحقق من البيانات (مخصص من الكود)
            logger.warning(f"Validation Error: {e}")
            return {
                'success': False,
                'data': {'error': str(e)},
                'status': 400
            }

        except IntegrityError as e:
            # خطأ في قاعدة البيانات (مثل تكرار إيميل، مفتاح خارجي مفقود)
            logger.error(f"Database Integrity Error: {e}")
            return {
                'success': False,
                'data': {'error': 'بيانات موجودة مسبقاً أو تعارض في النظام.'},
                'status': 409  # Conflict
            }

        except Exception as e:
            # أي خطأ غير متوقع (لمنع توقف التطبيق بالكامل)
            logger.exception(f"Unexpected Error in ViewModel: {e}") # يطبع التفاصيل في اللوجات
            return {
                'success': False,
                'data': {'error': 'حدث خطأ في الخادم، يرجى المحاولة لاحقاً.'},
                'status': 500
            }