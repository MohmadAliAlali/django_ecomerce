from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from app.common.exceptions import BusinessRuleError, ConcurrentUpdateError


def api_exception_handler(exc, context):
    if isinstance(exc, ConcurrentUpdateError):
        return Response(
            {'detail': 'Concurrent update detected. Please retry.'},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, BusinessRuleError):
        return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

    response = exception_handler(exc, context)

    if isinstance(exc, ValidationError) and response is not None:
        detail = response.data
        messages = []
        if isinstance(detail, dict):
            for field_errors in detail.values():
                if isinstance(field_errors, list):
                    messages.extend(str(item) for item in field_errors)
                else:
                    messages.append(str(field_errors))
        elif isinstance(detail, list):
            messages.extend(str(item) for item in detail)
        else:
            messages.append(str(detail))

        if any(
            token in message
            for message in messages
            for token in ('رصيد', 'مخزون', 'stock', 'balance', 'تعارض')
        ):
            response.status_code = status.HTTP_409_CONFLICT

    return response
