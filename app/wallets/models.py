from django.db import models

class Wallet(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.user.username}'s Wallet"