FROM mcr.microsoft.com/devcontainers/python:3-3.14-trixie

ENV PYTHONUNBUFFERED 1

# تثبيت مكتبات بايثون وأدوات النظام المطلوبة وتنظيف الملفات المؤقتة
COPY requirements.txt /tmp/pip-tmp/

RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt \
    && rm -rf /tmp/pip-tmp \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    postgresql-client \
    <your-package-list-here> \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# [خطوة إضافية] إنشاء سكريبت لعمليات قاعدة البيانات لسهولة التنفيذ
# سيتم حفظ هذا الملف في المسار /usr/local/bin/db-tools
RUN echo '#!/bin/bash\n\
if [ "$1" = "migrate" ]; then\n\
    echo "Running Django Migrations..."\n\
    python manage.py migrate\n\
elif [ "$1" = "export" ]; then\n\
    echo "Exporting Database..."\n\
    # استخدام pg_dump لتصدير قاعدة البيانات إلى المجلد المشارك\n\
    # يتم حفظ الملف باسم يحتوي على التاريخ والوقت\n\
    pg_dump -h db -U postgres postgres > \\\n\
    "/workspaces/$PROJECT_FOLDER/db-backups/db_backup_$(date +%Y%m%d_%H%M%S).sql"\n\
    echo "Backup saved successfully."\n\
else\n\
    echo "Usage: db-tools [migrate|export]"\n\
fi' > /usr/local/bin/db-tools && chmod +x /usr/local/bin/db-tools