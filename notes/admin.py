from django.contrib import admin

from .models import SalaryDeduction, Shift, ShiftType, Staff, StaffSalaryDeduction


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('management_number', 'name', 'hourly_wage', 'created_at')
    search_fields = ('management_number', 'name')


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'work_date',
        'staff',
        'shift_type',
        'start_time',
        'end_time',
        'actual_start_time',
        'actual_end_time',
        'role',
    )
    list_filter = ('work_date', 'staff', 'shift_type')
    search_fields = ('staff__name', 'role', 'memo')


@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'color', 'start_time', 'end_time', 'break_minutes')
    search_fields = ('code',)


@admin.register(SalaryDeduction)
class SalaryDeductionAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount_type', 'direction', 'fixed_amount')
    search_fields = ('name',)


@admin.register(StaffSalaryDeduction)
class StaffSalaryDeductionAdmin(admin.ModelAdmin):
    list_display = ('staff', 'deduction', 'amount', 'is_active')
    list_filter = ('deduction',)
    search_fields = ('staff__name', 'deduction__name')
