from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import Invoice, InvoiceItem, WeeklyReport
from .tasks import generate_weekly_report


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):

    list_display = ('id', 'user', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__username', 'user__email')


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):

    list_display = ('id', 'invoice', 'product_name', 'quantity', 'price')
    search_fields = ('product_name', 'invoice__id')


@admin.register(WeeklyReport)
class WeeklyReportAdmin(admin.ModelAdmin):
	change_list_template = 'admin/invoices/weeklyreport/change_list.html'

	list_display = ('id', 'week_start', 'week_end', 'total_sales', 'total_orders', 'created_at')
	actions = ['generate_report_now']

	def get_urls(self):
		urls = super().get_urls()
		custom = [
			path('generate-report/', self.admin_site.admin_view(self.generate_report_view), name='invoices_weeklyreport_generate_report'),
		]
		return custom + urls

	def generate_report_view(self, request):
		generate_weekly_report.delay()
		self.message_user(request, 'Weekly report generation queued.', level=messages.SUCCESS)
		return redirect(reverse('admin:invoices_weeklyreport_changelist'))

	def changelist_view(self, request, extra_context=None):
		extra_context = extra_context or {}
		extra_context['generate_report_url'] = reverse('admin:invoices_weeklyreport_generate_report')
		return super().changelist_view(request, extra_context=extra_context)

	def generate_report_now(self, request, queryset):
		# queue a report generation (ignores queryset, it's a global action)
		generate_weekly_report.delay()
		self.message_user(request, 'Weekly report generation queued.', level=messages.SUCCESS)

	generate_report_now.short_description = 'Generate weekly report now'
