from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallets', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='version',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
