from celery import shared_task
from django.contrib.auth.models import User
from django.core.paginator import Paginator


@shared_task
def send_notifications_batch(user_ids):

    users = User.objects.filter(id__in=user_ids)

    for user in users:

        print(f"Notification sent to {user.email}")


@shared_task
def weekly_notifications():

    users =  User.objects.order_by('id').values_list('id', flat=True)

    BATCH_SIZE = 500

    paginator = Paginator(users, BATCH_SIZE)

    for page_number in paginator.page_range:

        batch_ids = list(
            paginator.page(page_number).object_list
        )

        send_notifications_batch.delay(batch_ids)