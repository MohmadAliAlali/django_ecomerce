import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce.settings')

app = Celery('e_commerce')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {

    'send-weekly-notifications': {

        'task': 'app.product.tasks.weekly_notifications',

        'schedule': crontab(
            hour=12,
            minute=0,
            day_of_week='monday'
        ),
    },
}