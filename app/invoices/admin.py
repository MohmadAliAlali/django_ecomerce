from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import Invoice, InvoiceItem, SalesReport
from .tasks import generate_daily_sales_report


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'total_amount', 'status', 'created_at')
	list_filter = ('status', 'created_at')
	search_fields = ('id', 'user__username', 'user__email')


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
	list_display = ('id', 'invoice', 'product_name', 'quantity', 'price')
	search_fields = ('product_name', 'invoice__id')


@admin.register(SalesReport)
class SalesReportAdmin(admin.ModelAdmin):
	change_list_template = 'admin/invoices/salesreport/change_list.html'
	list_display = ('date', 'total_revenue', 'total_orders', 'avg_order_value', 'created_at')
	ordering = ('-date',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path('generate-report/', self.admin_site.admin_view(self.generate_report_view), name='invoices_salesreport_generate_report'),
		]
		return custom_urls + urls

	def generate_report_view(self, request):
		if request.method != 'POST':
			return redirect('admin:invoices_salesreport_changelist')

		report_id = generate_daily_sales_report.apply().get()
		self.message_user(request, f'Sales report generated successfully (ID: {report_id}).', level=messages.SUCCESS)
		return redirect('admin:invoices_salesreport_changelist')

	def changelist_view(self, request, extra_context=None):
		extra_context = extra_context or {}
		extra_context['generate_report_url'] = reverse('admin:invoices_salesreport_generate_report')
		return super().changelist_view(request, extra_context=extra_context)
