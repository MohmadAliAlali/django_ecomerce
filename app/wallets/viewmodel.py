from helper.viewmodel import BaseViewModel  
from .serializers import WalletSerializer

class WalletViewModel(BaseViewModel):
    serializer_class = WalletSerializer

    def perform_action(self):
        request = self.context.get('request')
        if not request:
            raise Exception("Request context is required")
            
        wallet = self.serializer.save(user=request.user)        
        return {'wallet_id': wallet.id, 'message': 'Wallet created successfully'}