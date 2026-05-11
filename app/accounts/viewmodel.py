# viewmodels/signup_viewmodel.py
from helper.viewmodel import BaseViewModel

from .serializers import SignupSerializer

class SignupViewModel(BaseViewModel):
    serializer_class = SignupSerializer

    def perform_action(self):
        user = self.serializer.save()        
        return {'user_id': user.id, 'email': user.email}