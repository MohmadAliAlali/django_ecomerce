from .serializers import WalletSerializer
from rest_framework import generics

class WalletCreateView(generics.CreateAPIView):
    serializer_class = WalletSerializer
    
