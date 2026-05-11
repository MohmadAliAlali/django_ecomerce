import json
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path


def _get_report_path():
    report_path = getattr(settings, "PERF_REPORT_PATH", None)
    if report_path:
        return Path(report_path)
    return Path(settings.BASE_DIR) / "performance-report.json"


def _load_report(path):
    if not path.exists():
        return None, "Report file not found. Run tests to generate it."

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle), None
    except OSError as exc:
        return None, f"Could not read report file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"Report file is not valid JSON: {exc}"


def performance_report_view(request):
    report_path = _get_report_path()
    report, load_error = _load_report(report_path)

    if request.GET.get("download") == "1" and report:
        response = HttpResponse(
            json.dumps(report, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = "attachment; filename=performance-report.json"
        return response

    context = {
        **admin.site.each_context(request),
        "title": "Performance Report",
        "report": report,
        "summary": report.get("summary", "") if report else "",
        "report_path": str(report_path),
        "load_error": load_error,
    }
    return TemplateResponse(request, "admin/performance_report.html", context)


def _register_admin_view():
    if getattr(admin.site, "_perf_report_installed", False):
        return

    original_get_urls = admin.site.get_urls

    def get_urls():
        urls = original_get_urls()
        custom = [
            path(
                "performance-report/",
                admin.site.admin_view(performance_report_view),
                name="performance-report",
            ),
        ]
        return custom + urls

    admin.site.get_urls = get_urls
    admin.site._perf_report_installed = True


_register_admin_view()
