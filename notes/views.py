import calendar
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    BREAK_MINUTE_CHOICES,
    SHIFT_TYPE_CODES,
    SHIFT_TYPE_COLOR_VALUES,
    SHIFT_TYPE_COLORS,
    DEDUCTION_AMOUNT_TYPES,
    SALARY_AMOUNT_DIRECTIONS,
    SalaryDeduction,
    Shift,
    ShiftType,
    Staff,
    StaffSalaryDeduction,
)


def shift_table(request):
    selected_month = _parse_month(request.GET.get('month'))
    first_day = selected_month.replace(day=1)
    last_day = selected_month.replace(day=calendar.monthrange(selected_month.year, selected_month.month)[1])
    previous_month = (first_day - timedelta(days=1)).replace(day=1)
    next_month = (last_day + timedelta(days=1)).replace(day=1)
    is_edit_mode = request.GET.get('mode') == 'edit'

    if request.method == 'POST':
        _save_bulk_shifts(request, first_day, last_day)
        messages.success(request, 'シフトを一括保存しました。')
        return redirect(f'{request.path}?month={selected_month:%Y-%m}')

    staff_members = Staff.objects.all()
    shifts = Shift.objects.filter(work_date__range=(first_day, last_day)).select_related('staff')
    shift_map = {(shift.staff_id, shift.work_date): shift for shift in shifts}
    shift_types = ShiftType.objects.all()
    role_choices = ['店内・トイレ掃除', '店内掃除', '銀行・トイレ掃除']

    calendar_weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(selected_month.year, selected_month.month)
    weeks = []
    for week_days in calendar_weeks:
        day_headers = [
            {
                'date': day,
                'url_date': f'{day:%Y-%m-%d}',
                'class_name': _calendar_day_class(day, selected_month),
            }
            for day in week_days
        ]
        week_rows = [
            {
                'staff': staff,
                'cells': [
                    {
                        'day': day,
                        'is_current_month': day.month == selected_month.month,
                        'class_name': _calendar_day_class(day, selected_month),
                        'shift': shift_map.get((staff.id, day)),
                        'field_key': f'{staff.id}_{day:%Y%m%d}',
                    }
                    for day in week_days
                ],
            }
            for staff in staff_members
        ]
        weeks.append({'days': day_headers, 'rows': week_rows})

    return render(
        request,
        'notes/shift_table.html',
        {
            'weeks': weeks,
            'selected_month': selected_month,
            'previous_month': previous_month,
            'next_month': next_month,
            'staff_count': staff_members.count(),
            'is_edit_mode': is_edit_mode,
            'shift_types': shift_types,
            'role_choices': role_choices,
        },
    )


def staff_create(request):
    if request.method == 'POST':
        staff = _build_staff_from_request(request)
        if staff:
            if Staff.objects.filter(name=staff.name).exists():
                messages.info(request, '同じ名前のスタッフはすでに登録されています。')
            else:
                staff.save()
                messages.success(request, 'スタッフを追加しました。')
            return redirect('staff_list')
    return render(request, 'notes/staff_form.html', {'staff': None})


def staff_list(request):
    staff_members = Staff.objects.all()
    selected_year = _parse_year(request.GET.get('year'))
    years = _staff_stats_years(selected_year)
    shifts = Shift.objects.filter(work_date__year=selected_year).select_related('shift_type')

    staff_rows = []
    for staff in staff_members:
        monthly_stats = [
            {
                'month': month,
                'planned_minutes': 0,
                'actual_minutes': 0,
                'planned_duration': '0時間',
                'actual_duration': '0時間',
                'actual_difference': '（±0時間）',
                'work_days': 0,
                'holiday_days': 0,
            }
            for month in range(1, 13)
        ]
        staff_shifts = [shift for shift in shifts if shift.staff_id == staff.id]
        for shift in staff_shifts:
            stats = monthly_stats[shift.work_date.month - 1]
            if shift.shift_type and shift.shift_type.code == '休':
                stats['holiday_days'] += 1
            elif shift.start_time and shift.end_time:
                stats['work_days'] += 1
                planned_minutes = _shift_work_minutes(shift)
                stats['planned_minutes'] += planned_minutes
                stats['actual_minutes'] += _actual_shift_work_minutes(shift, planned_minutes)
            elif shift.actual_start_time and shift.actual_end_time:
                stats['work_days'] += 1
                stats['actual_minutes'] += _actual_shift_work_minutes(shift, 0)

        for stats in monthly_stats:
            stats['planned_duration'] = _format_minutes(stats['planned_minutes'])
            stats['actual_duration'] = _format_minutes(stats['actual_minutes'])
            stats['actual_difference'] = _format_signed_minutes(
                stats['actual_minutes'] - stats['planned_minutes']
            )

        staff_rows.append({'staff': staff, 'monthly_stats': monthly_stats})

    return render(
        request,
        'notes/staff_list.html',
        {
            'staff_rows': staff_rows,
            'selected_year': selected_year,
            'years': years,
        },
    )


def staff_update(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        updated_staff = _build_staff_from_request(request, staff=staff)
        if updated_staff:
            updated_staff.save()
            messages.success(request, 'スタッフを更新しました。')
            return redirect('staff_list')
    return render(request, 'notes/staff_form.html', {'staff': staff})


def salary_list(request):
    selected_month = _parse_month(request.GET.get('month'))
    first_day = selected_month.replace(day=1)
    last_day = selected_month.replace(day=calendar.monthrange(selected_month.year, selected_month.month)[1])
    previous_month = (first_day - timedelta(days=1)).replace(day=1)
    next_month = (last_day + timedelta(days=1)).replace(day=1)
    shifts = Shift.objects.filter(work_date__range=(first_day, last_day)).select_related('shift_type', 'staff')
    deductions = SalaryDeduction.objects.all()
    staff_deduction_settings = {
        (staff_amount.staff_id, staff_amount.deduction_id): staff_amount
        for staff_amount in StaffSalaryDeduction.objects.select_related('deduction', 'staff')
    }

    rows = []
    total_minutes = 0
    total_gross_amount = 0
    total_adjustment_amount = 0
    total_net_amount = 0
    for staff in Staff.objects.all():
        staff_minutes = 0
        for shift in shifts:
            if shift.staff_id != staff.id:
                continue
            staff_minutes += _salary_shift_minutes(shift)
        gross_amount = _salary_amount(staff_minutes, staff.hourly_wage)
        adjustment_amount = _staff_salary_adjustment_total(staff, deductions, staff_deduction_settings)
        net_amount = gross_amount + adjustment_amount
        rows.append(
            {
                'staff': staff,
                'work_duration': _format_minutes(staff_minutes),
                'gross_amount': _format_yen(gross_amount),
                'adjustment_amount': _format_yen(adjustment_amount, signed=True),
                'net_amount': _format_yen(net_amount),
            }
        )
        total_minutes += staff_minutes
        total_gross_amount += gross_amount
        total_adjustment_amount += adjustment_amount
        total_net_amount += net_amount

    return render(
        request,
        'notes/salary_list.html',
        {
            'rows': rows,
            'selected_month': selected_month,
            'previous_month': previous_month,
            'next_month': next_month,
            'total_duration': _format_minutes(total_minutes),
            'total_gross_amount': _format_yen(total_gross_amount),
            'total_adjustment_amount': _format_yen(total_adjustment_amount, signed=True),
            'total_net_amount': _format_yen(total_net_amount),
        },
    )


def salary_settings(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'create':
            deduction = _build_salary_deduction_from_request(request)
            if deduction:
                deduction.save()
                messages.success(request, '差引項目を追加しました。')
                return redirect('salary_settings')
        elif action == 'update':
            deduction = get_object_or_404(SalaryDeduction, pk=request.POST.get('deduction_id'))
            updated_deduction = _build_salary_deduction_from_request(request, deduction=deduction)
            if updated_deduction:
                updated_deduction.save()
                _save_deduction_targets(request, updated_deduction)
                messages.success(request, '差引項目を更新しました。')
                return redirect('salary_settings')
        elif action == 'delete':
            deduction = get_object_or_404(SalaryDeduction, pk=request.POST.get('deduction_id'))
            deduction.delete()
            messages.success(request, '差引項目を削除しました。')
            return redirect('salary_settings')

    deduction_rows = [
        {
            'deduction': deduction,
            'staff_targets': _salary_deduction_target_rows(deduction),
        }
        for deduction in SalaryDeduction.objects.all()
    ]

    return render(
        request,
        'notes/salary_settings.html',
        {
            'deduction_rows': deduction_rows,
            'amount_types': DEDUCTION_AMOUNT_TYPES,
            'amount_directions': SALARY_AMOUNT_DIRECTIONS,
        },
    )


def staff_salary_settings(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    deductions = SalaryDeduction.objects.all()
    staff_settings = {
        staff_amount.deduction_id: staff_amount
        for staff_amount in StaffSalaryDeduction.objects.filter(staff=staff)
    }

    if request.method == 'POST':
        hourly_wage = request.POST.get('hourly_wage', '').strip()
        try:
            parsed_hourly_wage = int(hourly_wage or 0)
        except ValueError:
            messages.error(request, '時給は0以上の整数で入力してください。')
            parsed_hourly_wage = None

        if parsed_hourly_wage is not None and parsed_hourly_wage < 0:
            messages.error(request, '時給は0以上の整数で入力してください。')
            parsed_hourly_wage = None

        if parsed_hourly_wage is not None:
            staff.hourly_wage = parsed_hourly_wage
            staff.save(update_fields=['hourly_wage'])
            for deduction in deductions:
                staff_amount, _created = StaffSalaryDeduction.objects.get_or_create(
                    staff=staff,
                    deduction=deduction,
                )
                staff_amount.is_active = request.POST.get(f'deduction_active_{deduction.id}') == 'on'
                amount_value = request.POST.get(f'deduction_amount_{deduction.id}', '').strip() if deduction.amount_type == 'variable' else str(staff_amount.amount)
                try:
                    amount = int(amount_value or 0)
                except ValueError:
                    amount = 0
                staff_amount.amount = max(0, amount)
                staff_amount.save()
            messages.success(request, 'スタッフ別給料設定を保存しました。')
            return redirect('salary_list')

    rows = [
        {
            'deduction': deduction,
            'amount': deduction.fixed_amount if deduction.amount_type == 'fixed' else staff_settings.get(deduction.id).amount if deduction.id in staff_settings else 0,
            'is_active': _salary_deduction_is_active(staff_settings.get(deduction.id), deduction),
            'is_fixed': deduction.amount_type == 'fixed',
            'direction_label': deduction.get_direction_display(),
        }
        for deduction in deductions
    ]

    return render(
        request,
        'notes/staff_salary_settings.html',
        {
            'staff': staff,
            'rows': rows,
        },
    )


def shift_type_list(request):
    shift_types = ShiftType.objects.all()
    used_codes = set(shift_types.values_list('code', flat=True))
    available_codes = [code for code, _label in SHIFT_TYPE_CODES if code not in used_codes]
    return render(
        request,
        'notes/shift_type_list.html',
        {'shift_types': shift_types, 'available_codes': available_codes},
    )


def shift_type_create(request):
    if request.method == 'POST':
        shift_type = _build_shift_type_from_request(request)
        if shift_type:
            shift_type.save()
            messages.success(request, '勤務区分を登録しました。')
            return redirect('shift_type_list')
    return render(
        request,
        'notes/shift_type_form.html',
        _shift_type_form_context(None),
    )


def shift_type_update(request, pk):
    shift_type = get_object_or_404(ShiftType, pk=pk)
    if request.method == 'POST':
        updated_shift_type = _build_shift_type_from_request(request, shift_type=shift_type)
        if updated_shift_type:
            updated_shift_type.save()
            messages.success(request, '勤務区分を更新しました。')
            return redirect('shift_type_list')
    return render(
        request,
        'notes/shift_type_form.html',
        _shift_type_form_context(shift_type),
    )


def shift_type_delete(request, pk):
    shift_type = get_object_or_404(ShiftType, pk=pk)
    if request.method == 'POST':
        shift_type.delete()
        messages.success(request, '勤務区分を削除しました。')
        return redirect('shift_type_list')
    return render(request, 'notes/shift_type_confirm_delete.html', {'shift_type': shift_type})


def shift_create(request):
    staff_members = Staff.objects.all()
    shift_types = ShiftType.objects.all()
    if request.method == 'POST':
        shift = _build_shift_from_request(request)
        if shift:
            existing = Shift.objects.filter(staff=shift.staff, work_date=shift.work_date).first()
            if existing:
                existing.shift_type = shift.shift_type
                existing.start_time = shift.start_time
                existing.end_time = shift.end_time
                existing.role = shift.role
                existing.memo = shift.memo
                existing.save()
                messages.success(request, '既存のシフトを更新しました。')
            else:
                shift.save()
                messages.success(request, 'シフトを登録しました。')
            return redirect(f"{request.POST.get('next', '/')}")
    return render(
        request,
        'notes/shift_form.html',
        {'shift': None, 'staff_members': staff_members, 'shift_types': shift_types},
    )


def actual_work_edit(request, work_date):
    try:
        target_date = datetime.strptime(work_date, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, '日付を確認してください。')
        return redirect('shift_table')

    staff_members = Staff.objects.all()
    shifts = {
        shift.staff_id: shift
        for shift in Shift.objects.filter(work_date=target_date).select_related('staff', 'shift_type')
    }

    if request.method == 'POST':
        if _save_actual_work_times(request, target_date, staff_members, shifts):
            messages.success(request, '実働時間を保存しました。')
            return redirect('actual_work_edit', work_date=f'{target_date:%Y-%m-%d}')

    rows = []
    for staff in staff_members:
        shift = shifts.get(staff.id)
        initial_start = shift.actual_start_time or shift.start_time if shift else None
        initial_end = shift.actual_end_time or shift.end_time if shift else None
        rows.append(
            {
                'staff': staff,
                'shift': shift,
                'is_day_off': shift.shift_type.code == '休' if shift and shift.shift_type else False,
                'planned_label': _shift_time_label(shift),
                'actual_start': initial_start,
                'actual_end': initial_end,
            }
        )

    return render(
        request,
        'notes/actual_work_form.html',
        {
            'target_date': target_date,
            'rows': rows,
        },
    )


def shift_update(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    staff_members = Staff.objects.all()
    shift_types = ShiftType.objects.all()
    if request.method == 'POST':
        updated_shift = _build_shift_from_request(request, shift=shift)
        if updated_shift:
            updated_shift.save()
            messages.success(request, 'シフトを更新しました。')
            return redirect('shift_table')
    return render(
        request,
        'notes/shift_form.html',
        {'shift': shift, 'staff_members': staff_members, 'shift_types': shift_types},
    )


def shift_delete(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    if request.method == 'POST':
        shift.delete()
        messages.success(request, 'シフトを削除しました。')
        return redirect('shift_table')
    return render(request, 'notes/shift_confirm_delete.html', {'shift': shift})


def _parse_month(value):
    if value:
        try:
            return datetime.strptime(value, '%Y-%m').date()
        except ValueError:
            messages = None
    return date.today().replace(day=1)


def _parse_year(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return timezone.localdate().year


def _staff_stats_years(selected_year):
    years = {selected_year, timezone.localdate().year}
    years.update(work_date.year for work_date in Shift.objects.values_list('work_date', flat=True))
    return sorted(years, reverse=True)


def _build_staff_from_request(request, staff=None):
    management_number = request.POST.get('management_number', '').strip()
    name = request.POST.get('name', '').strip()
    hourly_wage = request.POST.get('hourly_wage', '').strip()

    if not name:
        messages.error(request, 'スタッフ名を入力してください。')
        return None

    if hourly_wage:
        try:
            parsed_hourly_wage = int(hourly_wage)
        except ValueError:
            messages.error(request, '時給は0以上の整数で入力してください。')
            return None
        if parsed_hourly_wage < 0:
            messages.error(request, '時給は0以上の整数で入力してください。')
            return None
    else:
        parsed_hourly_wage = 0

    if management_number and (len(management_number) != 2 or not management_number.isdigit()):
        messages.error(request, '管理番号は2桁の数字で入力してください。')
        return None

    duplicate_number = Staff.objects.filter(management_number=management_number) if management_number else Staff.objects.none()
    duplicate_name = Staff.objects.filter(name=name)
    if staff:
        duplicate_number = duplicate_number.exclude(pk=staff.pk)
        duplicate_name = duplicate_name.exclude(pk=staff.pk)

    if duplicate_number.exists():
        messages.error(request, '同じ管理番号のスタッフはすでに登録されています。')
        return None

    if duplicate_name.exists():
        messages.error(request, '同じ名前のスタッフはすでに登録されています。')
        return None

    if staff is None:
        staff = Staff()
    staff.management_number = management_number or None
    staff.name = name
    staff.hourly_wage = parsed_hourly_wage
    return staff


def _salary_shift_minutes(shift):
    if shift.shift_type and shift.shift_type.code == '休':
        return 0
    if shift.start_time and shift.end_time:
        planned_minutes = _shift_work_minutes(shift)
        return _actual_shift_work_minutes(shift, planned_minutes)
    if shift.actual_start_time and shift.actual_end_time:
        return _actual_shift_work_minutes(shift, 0)
    return 0


def _salary_amount(minutes, hourly_wage):
    return minutes * hourly_wage // 60


def _staff_salary_adjustment_total(staff, deductions, staff_deduction_settings):
    total = 0
    for deduction in deductions:
        staff_setting = staff_deduction_settings.get((staff.id, deduction.id))
        if not _salary_deduction_is_active(staff_setting, deduction):
            continue
        if deduction.amount_type == 'fixed':
            amount = deduction.fixed_amount
        else:
            amount = staff_setting.amount if staff_setting else 0
        if deduction.direction == 'add':
            total += amount
        else:
            total -= amount
    return total


def _salary_deduction_is_active(staff_setting, deduction):
    if staff_setting is not None:
        return staff_setting.is_active
    return deduction.amount_type == 'fixed'


def _salary_deduction_target_rows(deduction):
    staff_settings = {
        staff_amount.staff_id: staff_amount
        for staff_amount in StaffSalaryDeduction.objects.filter(deduction=deduction)
    }
    return [
        {
            'staff': staff,
            'is_active': _salary_deduction_is_active(staff_settings.get(staff.id), deduction),
        }
        for staff in Staff.objects.all()
    ]


def _save_deduction_targets(request, deduction):
    for staff in Staff.objects.all():
        staff_amount, _created = StaffSalaryDeduction.objects.get_or_create(
            staff=staff,
            deduction=deduction,
        )
        staff_amount.is_active = request.POST.get(f'target_staff_{staff.id}') == 'on'
        staff_amount.save()


def _build_salary_deduction_from_request(request, deduction=None):
    name = request.POST.get('name', '').strip()
    amount_type = request.POST.get('amount_type', '').strip()
    direction = request.POST.get('direction', '').strip()
    fixed_amount = request.POST.get('fixed_amount', '').strip()

    if not name:
        messages.error(request, '項目名を入力してください。')
        return None

    if amount_type not in dict(DEDUCTION_AMOUNT_TYPES):
        messages.error(request, '固定または変動を選択してください。')
        return None

    if direction not in dict(SALARY_AMOUNT_DIRECTIONS):
        messages.error(request, '＋または−を選択してください。')
        return None

    try:
        parsed_fixed_amount = int(fixed_amount or 0)
    except ValueError:
        messages.error(request, '金額は0以上の整数で入力してください。')
        return None
    if parsed_fixed_amount < 0:
        messages.error(request, '金額は0以上の整数で入力してください。')
        return None

    duplicate = SalaryDeduction.objects.filter(name=name)
    if deduction:
        duplicate = duplicate.exclude(pk=deduction.pk)
    if duplicate.exists():
        messages.error(request, '同じ項目名はすでに登録されています。')
        return None

    if deduction is None:
        deduction = SalaryDeduction()
    deduction.name = name
    deduction.amount_type = amount_type
    deduction.direction = direction
    deduction.fixed_amount = parsed_fixed_amount
    return deduction


def _format_yen(amount, signed=False):
    if signed:
        if amount > 0:
            return f'+{amount:,}円'
        if amount < 0:
            return f'-{abs(amount):,}円'
        return '±0円'
    return f'{amount:,}円'


def _shift_work_minutes(shift):
    break_minutes = shift.shift_type.break_minutes if shift.shift_type and shift.shift_type.break_minutes else 0
    return _time_range_minutes(shift.start_time, shift.end_time, break_minutes)


def _actual_shift_work_minutes(shift, fallback_minutes):
    if not shift.actual_start_time or not shift.actual_end_time:
        return fallback_minutes
    break_minutes = shift.shift_type.break_minutes if shift.shift_type and shift.shift_type.break_minutes else 0
    return _time_range_minutes(shift.actual_start_time, shift.actual_end_time, break_minutes)


def _time_range_minutes(start_time, end_time, break_minutes=0):
    start_at = datetime.combine(datetime.today(), start_time)
    end_at = datetime.combine(datetime.today(), end_time)
    minutes = int((end_at - start_at).total_seconds() // 60)
    return max(0, minutes - break_minutes)


def _format_minutes(minutes):
    hours, remainder = divmod(minutes, 60)
    if not hours and remainder:
        return f'{remainder}分'
    if remainder:
        return f'{hours}時間{remainder}分'
    return f'{hours}時間'


def _format_signed_minutes(minutes):
    if minutes == 0:
        return '（±0時間）'
    sign = '+' if minutes > 0 else '-'
    return f'（{sign}{_format_minutes(abs(minutes))}）'


def _shift_time_label(shift):
    if not shift:
        return '予定なし'
    if shift.shift_type and shift.shift_type.code == '休':
        return '休'
    if shift.start_time and shift.end_time:
        return f'{shift.start_time:%H:%M}-{shift.end_time:%H:%M}'
    return '時間なし'


def _calendar_day_class(day, selected_month):
    classes = []
    if day.month != selected_month.month:
        classes.append('outside-month')
    if day.weekday() == 5:
        classes.append('saturday-cell')
    if day.weekday() == 6 or day in _japanese_holidays(day.year):
        classes.append('holiday-cell')
    return ' '.join(classes)


def _japanese_holidays(year):
    holidays = {
        date(year, 1, 1),
        _nth_weekday(year, 1, 0, 2),
        date(year, 2, 11),
        date(year, 2, 23),
        _vernal_equinox(year),
        date(year, 4, 29),
        date(year, 5, 3),
        date(year, 5, 4),
        date(year, 5, 5),
        _nth_weekday(year, 7, 0, 3),
        date(year, 8, 11),
        _nth_weekday(year, 9, 0, 3),
        _autumnal_equinox(year),
        _nth_weekday(year, 10, 0, 2),
        date(year, 11, 3),
        date(year, 11, 23),
    }

    all_holidays = set(holidays)
    for holiday in sorted(holidays):
        if holiday.weekday() == 6:
            substitute = holiday + timedelta(days=1)
            while substitute in all_holidays:
                substitute += timedelta(days=1)
            all_holidays.add(substitute)

    current = date(year, 1, 2)
    end = date(year, 12, 30)
    while current <= end:
        if current not in all_holidays and current - timedelta(days=1) in all_holidays and current + timedelta(days=1) in all_holidays:
            all_holidays.add(current)
        current += timedelta(days=1)

    return all_holidays


def _nth_weekday(year, month, weekday, n):
    current = date(year, month, 1)
    days_until_weekday = (weekday - current.weekday()) % 7
    return current + timedelta(days=days_until_weekday + (n - 1) * 7)


def _vernal_equinox(year):
    day = int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    return date(year, 3, day)


def _autumnal_equinox(year):
    day = int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    return date(year, 9, day)


def _build_shift_from_request(request, shift=None):
    staff_id = request.POST.get('staff')
    shift_type_id = request.POST.get('shift_type')
    work_date = request.POST.get('work_date', '').strip()
    start_time = request.POST.get('start_time', '').strip()
    end_time = request.POST.get('end_time', '').strip()
    role = request.POST.get('role', '').strip()
    memo = request.POST.get('memo', '').strip()

    if not staff_id or not work_date:
        messages.error(request, 'スタッフと勤務日を入力してください。')
        return None

    try:
        staff = Staff.objects.get(pk=staff_id)
        shift_type = ShiftType.objects.get(pk=shift_type_id) if shift_type_id else None
        parsed_date = datetime.strptime(work_date, '%Y-%m-%d').date()
    except (Staff.DoesNotExist, ShiftType.DoesNotExist, ValueError):
        messages.error(request, '入力内容を確認してください。')
        return None

    is_day_off = shift_type is not None and shift_type.code == '休'
    parsed_start = None
    parsed_end = None
    if not is_day_off:
        if not start_time or not end_time:
            messages.error(request, '開始時刻と終了時刻を入力してください。')
            return None
        try:
            parsed_start = datetime.strptime(start_time, '%H:%M').time()
            parsed_end = datetime.strptime(end_time, '%H:%M').time()
        except ValueError:
            messages.error(request, '時刻の形式を確認してください。')
            return None
        if parsed_start >= parsed_end:
            messages.error(request, '終了時刻は開始時刻より後にしてください。')
            return None

    if shift is None:
        shift = Shift()
    shift.staff = staff
    shift.shift_type = shift_type
    shift.work_date = parsed_date
    shift.start_time = parsed_start
    shift.end_time = parsed_end
    shift.role = role
    shift.memo = memo
    return shift


def _save_actual_work_times(request, work_date, staff_members, existing_shifts):
    has_error = False
    pending_updates = []
    for staff in staff_members:
        start_value = request.POST.get(f'actual_start_{staff.id}', '').strip()
        end_value = request.POST.get(f'actual_end_{staff.id}', '').strip()
        shift = existing_shifts.get(staff.id)

        if not start_value and not end_value:
            if shift:
                pending_updates.append((shift, None, None))
            continue

        if not start_value or not end_value:
            messages.error(request, f'{staff.name}さんの開始時刻と終了時刻を両方入力してください。')
            has_error = True
            continue

        try:
            actual_start = datetime.strptime(start_value, '%H:%M').time()
            actual_end = datetime.strptime(end_value, '%H:%M').time()
        except ValueError:
            messages.error(request, f'{staff.name}さんの時刻の形式を確認してください。')
            has_error = True
            continue

        if actual_start >= actual_end:
            messages.error(request, f'{staff.name}さんの終了時刻は開始時刻より後にしてください。')
            has_error = True
            continue

        if shift is None:
            shift = Shift(staff=staff, work_date=work_date)
            existing_shifts[staff.id] = shift
        pending_updates.append((shift, actual_start, actual_end))

    if has_error:
        return False

    for shift, actual_start, actual_end in pending_updates:
        shift.actual_start_time = actual_start
        shift.actual_end_time = actual_end
        shift.save()

    return True


def _save_bulk_shifts(request, first_day, last_day):
    staff_members = Staff.objects.all()
    shift_types = {str(shift_type.pk): shift_type for shift_type in ShiftType.objects.all()}
    existing_shifts = {
        (shift.staff_id, shift.work_date): shift
        for shift in Shift.objects.filter(work_date__range=(first_day, last_day))
    }

    current = first_day
    days = []
    while current <= last_day:
        days.append(current)
        current += timedelta(days=1)

    for staff in staff_members:
        for work_date in days:
            key = f'{staff.id}_{work_date:%Y%m%d}'
            shift_type_id = request.POST.get(f'shift_type_{key}', '').strip()
            role = request.POST.get(f'role_{key}', '').strip()
            existing_shift = existing_shifts.get((staff.id, work_date))

            if not shift_type_id:
                continue

            shift_type = shift_types.get(shift_type_id)
            if shift_type is None:
                continue

            shift = existing_shift or Shift(staff=staff, work_date=work_date)
            shift.shift_type = shift_type
            if shift_type.code == '休':
                shift.start_time = None
                shift.end_time = None
                shift.role = ''
            else:
                shift.start_time = shift_type.start_time
                shift.end_time = shift_type.end_time
                shift.role = role
            shift.save()


def _build_shift_type_from_request(request, shift_type=None):
    code = request.POST.get('code', '').strip().upper()
    name = request.POST.get('name', '').strip()
    color = request.POST.get('color', '').strip()
    start_time = request.POST.get('start_time', '').strip()
    end_time = request.POST.get('end_time', '').strip()
    break_minutes = request.POST.get('break_minutes', '').strip()

    if code not in dict(SHIFT_TYPE_CODES):
        messages.error(request, '区分は休またはA〜Zから選択してください。')
        return None

    if code != '休' and color not in SHIFT_TYPE_COLOR_VALUES:
        messages.error(request, '色を選択してください。')
        return None

    if code == '休':
        color = ''
        break_minutes = ''

    if color:
        duplicate_color = ShiftType.objects.filter(color=color)
        if shift_type:
            duplicate_color = duplicate_color.exclude(pk=shift_type.pk)
        if duplicate_color.exists():
            messages.error(request, 'この色はすでに使用されています。')
            return None

    parsed_start = None
    parsed_end = None
    parsed_break_minutes = None
    if code != '休' and (not start_time or not end_time):
        messages.error(request, '開始時刻と終了時刻を入力してください。')
        return None

    break_values = {str(value) for value, _label in BREAK_MINUTE_CHOICES}
    if code != '休' and break_minutes not in break_values:
        messages.error(request, '休憩時間を選択してください。')
        return None
    if break_minutes:
        parsed_break_minutes = int(break_minutes)

    if start_time or end_time:
        try:
            parsed_start = datetime.strptime(start_time, '%H:%M').time() if start_time else None
            parsed_end = datetime.strptime(end_time, '%H:%M').time() if end_time else None
        except ValueError:
            messages.error(request, '時刻の形式を確認してください。')
            return None

        if parsed_start and parsed_end and parsed_start >= parsed_end:
            messages.error(request, '終了時刻は開始時刻より後にしてください。')
            return None

    duplicate = ShiftType.objects.filter(code=code)
    if shift_type:
        duplicate = duplicate.exclude(pk=shift_type.pk)
    if duplicate.exists():
        messages.error(request, f'区分{code}はすでに登録されています。')
        return None

    if shift_type is None:
        shift_type = ShiftType()
    shift_type.code = code
    shift_type.name = name
    shift_type.color = None if code == '休' else color
    shift_type.start_time = None if code == '休' else parsed_start
    shift_type.end_time = None if code == '休' else parsed_end
    shift_type.break_minutes = None if code == '休' else parsed_break_minutes
    return shift_type


def _shift_type_form_context(shift_type):
    used_colors = set(ShiftType.objects.exclude(color__isnull=True).values_list('color', flat=True))
    if shift_type and shift_type.color:
        used_colors.discard(shift_type.color)
    colors = [
        {
            'value': color,
            'label': label,
            'is_used': color in used_colors,
            'is_selected': bool(shift_type and shift_type.color == color),
        }
        for color, label in SHIFT_TYPE_COLORS
    ]
    return {
        'shift_type': shift_type,
        'codes': SHIFT_TYPE_CODES,
        'colors': colors,
        'break_choices': BREAK_MINUTE_CHOICES,
    }
