FROM mcr.microsoft.com/devcontainers/python:3-3.14-trixie

ENV PYTHONUNBUFFERED 1

# تثبيت مكتبات بايثون، أدوات النظام، وإنشاء سكريبت أدوات قاعدة البيانات في خطوة واحدة
COPY requirements.txt /tmp/pip-tmp/

RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt \
    && rm -rf /tmp/pip-tmp \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    postgresql-client \
    <your-package-list-here> \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && echo '#!/bin/bash\n\
if [ "$1" = "migrate" ]; then\n\
    echo "Running Django Migrations..."\n\
    python manage.py migrate\n\
elif [ "$1" = "export" ]; then\n\
    echo "Exporting Database..."\n\' > /usr/local/bin/db-tools && chmod +x /usr/local/bin/db-tools
