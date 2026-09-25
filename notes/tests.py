from django.test import TestCase
from django.urls import reverse

from .models import SalaryDeduction, Shift, ShiftType, Staff, StaffSalaryDeduction, MonthlyStaffSalaryDeduction


class ShiftViewTests(TestCase):
    def test_reset_command_preserves_past_and_resets_future(self):
        from datetime import date
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command

        staff = Staff.objects.create(name='Command test')
        deduction = SalaryDeduction.objects.create(name='Fixed allowance', amount_type='fixed', fixed_amount=1000)
        past = MonthlyStaffSalaryDeduction.objects.create(
            staff=staff, deduction=deduction, month='2026-09-01', amount=800, is_active=True,
        )
        future = MonthlyStaffSalaryDeduction.objects.create(
            staff=staff, deduction=deduction, month='2027-01-01', amount=900, is_active=True,
        )
        with patch('notes.management.commands.reset_salary_adjustments.backup_database', return_value='backup.sqlite3') as backup:
            call_command('reset_salary_adjustments', from_month='2026-10', stdout=StringIO())
            backup.assert_not_called()
            self.assertFalse(StaffSalaryDeduction.objects.exists())
            call_command('reset_salary_adjustments', from_month='2026-10', apply=True, stdout=StringIO())
            backup.assert_called_once()
        setting = StaffSalaryDeduction.objects.get(staff=staff, deduction=deduction)
        self.assertTrue(setting.for_month(date(2026, 8, 1)).is_active)
        self.assertEqual(setting.amount, 1000)
        self.assertFalse(setting.for_month(date(2030, 1, 1)).is_active)
        self.assertEqual(setting.for_month(date(2030, 1, 1)).amount, 0)
        past.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual((past.amount, past.is_active), (800, True))
        self.assertEqual((future.amount, future.is_active), (0, False))

    def test_adjustment_reset_preserves_past_and_allows_month_override(self):
        staff = Staff.objects.create(name='Reset test')
        deduction = SalaryDeduction.objects.create(name='Allowance', amount_type='variable', direction='add')
        StaffSalaryDeduction.objects.create(
            staff=staff, deduction=deduction, amount=1000, is_active=True,
            reset_from_month='2026-10-01',
        )
        for month, expected in [('2026-09', 1000), ('2026-10', 0), ('2028-01', 0)]:
            response = self.client.get(reverse('salary_list'), {'month': month})
            from .views import _format_yen
            self.assertEqual(response.context['rows'][0]['adjustment_amount'], _format_yen(expected, signed=True))
        MonthlyStaffSalaryDeduction.objects.create(
            staff=staff, deduction=deduction, month='2026-11-01', amount=500, is_active=True,
        )
        response = self.client.get(reverse('salary_list'), {'month': '2026-11'})
        self.assertEqual(response.context['rows'][0]['adjustment_amount'], _format_yen(500, signed=True))

    def setUp(self):
        ShiftType.objects.all().delete()

    def test_can_create_staff(self):
        response = self.client.post(
            reverse('staff_create'),
            {'management_number': '02', 'name': '田中'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Staff.objects.count(), 1)
        self.assertEqual(Staff.objects.get().management_number, '02')
        self.assertEqual(Staff.objects.get().hourly_wage, 0)
        self.assertNotContains(response, 'No. 02')
        self.assertContains(response, '田中')

    def test_can_update_staff(self):
        staff = Staff.objects.create(management_number='02', name='田中')

        response = self.client.post(
            reverse('staff_update', args=[staff.pk]),
            {'management_number': '01', 'name': '佐藤', 'hourly_wage': '1200'},
            follow=True,
        )

        staff.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(staff.management_number, '01')
        self.assertEqual(staff.name, '佐藤')
        self.assertEqual(staff.hourly_wage, 1200)
        self.assertNotContains(response, 'No. 01')
        self.assertContains(response, '佐藤')

    def test_staff_list_orders_by_management_number(self):
        Staff.objects.create(management_number='03', name='田中')
        Staff.objects.create(management_number='01', name='佐藤')
        Staff.objects.create(name='山田')

        response = self.client.get(reverse('staff_list'))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'No. 01')
        self.assertNotContains(response, 'No. 03')
        self.assertLess(content.index('佐藤'), content.index('田中'))
        self.assertLess(content.index('田中'), content.index('山田'))

    def test_staff_management_number_must_be_two_digits(self):
        response = self.client.post(
            reverse('staff_create'),
            {'management_number': '1', 'name': '田中'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Staff.objects.count(), 0)
        self.assertContains(response, '管理番号は2桁の数字で入力してください。')

    def test_staff_hourly_wage_must_be_positive_integer(self):
        response = self.client.post(
            reverse('staff_create'),
            {'management_number': '01', 'name': '田中', 'hourly_wage': '-1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Staff.objects.count(), 0)
        self.assertContains(response, '時給は0以上の整数で入力してください。')

    def test_salary_list_shows_monthly_salary_from_actual_work(self):
        staff = Staff.objects.create(name='田中', hourly_wage=1200)
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        Shift.objects.create(
            staff=staff,
            shift_type=shift_type,
            work_date='2026-09-01',
            start_time='09:00',
            end_time='17:00',
            actual_start_time='09:00',
            actual_end_time='18:00',
        )

        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2026年9月の給料')
        self.assertContains(response, '田中')
        self.assertContains(response, '07.75h')
        self.assertContains(response, '9,300円')

    def test_salary_list_reflects_fixed_and_variable_deductions(self):
        staff = Staff.objects.create(name='田中', hourly_wage=1200)
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        Shift.objects.create(
            staff=staff,
            shift_type=shift_type,
            work_date='2026-09-01',
            start_time='09:00',
            end_time='17:00',
        )
        SalaryDeduction.objects.create(name='所得税', amount_type='fixed', direction='subtract', fixed_amount=500)
        variable = SalaryDeduction.objects.create(name='調整', amount_type='variable', direction='subtract')
        StaffSalaryDeduction.objects.create(staff=staff, deduction=variable, amount=200)

        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '8,400円')
        self.assertContains(response, '-700円')
        self.assertContains(response, '7,700円')

    def test_salary_list_reflects_addition_deduction(self):
        staff = Staff.objects.create(name='田中', hourly_wage=1200)
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        Shift.objects.create(
            staff=staff,
            shift_type=shift_type,
            work_date='2026-09-01',
            start_time='09:00',
            end_time='17:00',
        )
        transportation = SalaryDeduction.objects.create(name='交通費', amount_type='variable', direction='add')
        StaffSalaryDeduction.objects.create(staff=staff, deduction=transportation, amount=1000)

        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '8,400円')
        self.assertContains(response, '+1,000円')
        self.assertContains(response, '9,400円')

    def test_can_create_salary_deduction_setting(self):
        response = self.client.post(
            reverse('salary_settings'),
            {
                'action': 'create',
                'name': '所得税',
                'direction': 'subtract',
                'amount_type': 'fixed',
                'fixed_amount': '500',
            },
            follow=True,
        )

        deduction = SalaryDeduction.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(deduction.name, '所得税')
        self.assertEqual(deduction.amount_type, 'fixed')
        self.assertEqual(deduction.fixed_amount, 500)
        self.assertContains(response, '差引項目を追加しました。')

    def test_can_save_staff_salary_settings(self):
        staff = Staff.objects.create(name='田中', hourly_wage=1000)
        deduction = SalaryDeduction.objects.create(name='調整', amount_type='variable')

        response = self.client.post(
            reverse('staff_salary_settings', args=[staff.pk]),
            {
                'hourly_wage': '1300',
                f'deduction_active_{deduction.pk}': 'on',
                f'deduction_amount_{deduction.pk}': '300',
            },
            follow=True,
        )

        staff.refresh_from_db()
        staff_deduction = MonthlyStaffSalaryDeduction.objects.get(staff=staff, deduction=deduction)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(staff.hourly_wage, 1300)
        self.assertTrue(staff_deduction.is_active)
        self.assertEqual(staff_deduction.amount, 300)
        self.assertContains(response, 'スタッフ別給料設定を保存しました。')

    def test_can_turn_salary_deduction_target_off_from_global_settings(self):
        staff = Staff.objects.create(name='田中', hourly_wage=1200)
        deduction = SalaryDeduction.objects.create(
            name='所得税',
            amount_type='fixed',
            direction='subtract',
            fixed_amount=500,
        )

        response = self.client.post(
            reverse('salary_settings'),
            {
                'action': 'update',
                'deduction_id': deduction.pk,
                'name': '所得税',
                'direction': 'subtract',
                'amount_type': 'fixed',
                'fixed_amount': '500',
            },
            follow=True,
        )

        staff_deduction = StaffSalaryDeduction.objects.get(staff=staff, deduction=deduction)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(staff_deduction.is_active)

    def test_staff_stats_show_monthly_work_and_holiday_counts(self):
        staff = Staff.objects.create(name='田中')
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        holiday_type = ShiftType.objects.create(code='休')
        Shift.objects.create(
            staff=staff,
            shift_type=shift_type,
            work_date='2026-09-01',
            start_time='09:00',
            end_time='17:00',
            actual_start_time='09:30',
            actual_end_time='18:00',
        )
        Shift.objects.create(
            staff=staff,
            shift_type=holiday_type,
            work_date='2026-09-02',
        )

        response = self.client.get(reverse('staff_list'), {'year': '2026'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '田中さんの稼働状況')
        self.assertContains(response, '予定時間')
        self.assertContains(response, '実働時間')
        self.assertContains(response, '7時間')
        self.assertContains(response, '7時間30分')
        self.assertContains(response, '（+30分）')
        self.assertContains(response, '1日')

    def test_can_create_shift(self):
        staff = Staff.objects.create(name='佐藤')
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )

        response = self.client.post(
            reverse('shift_create'),
            {
                'staff': staff.pk,
                'shift_type': shift_type.pk,
                'work_date': '2026-09-21',
                'start_time': '09:00',
                'end_time': '17:00',
                'role': '店内・トイレ掃除',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Shift.objects.count(), 1)
        self.assertEqual(Shift.objects.get().shift_type, shift_type)
        self.assertContains(response, '09:00-17:00')

    def test_calendar_marks_saturday_and_holiday_headers(self):
        Staff.objects.create(name='佐藤')

        response = self.client.get(reverse('shift_table'), {'month': '2026-09'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'saturday-cell')
        self.assertContains(response, 'holiday-cell')
        self.assertContains(response, reverse('actual_work_edit', args=['2026-09-21']))

    def test_can_bulk_save_shift_from_calendar_edit_mode(self):
        staff = Staff.objects.create(name='佐藤')
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )

        response = self.client.post(
            reverse('shift_table') + '?month=2026-09&mode=edit',
            {
                f'shift_type_{staff.pk}_20260921': str(shift_type.pk),
                f'role_{staff.pk}_20260921': '店内掃除',
            },
            follow=True,
        )

        shift = Shift.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(shift.staff, staff)
        self.assertEqual(shift.shift_type, shift_type)
        self.assertEqual(str(shift.work_date), '2026-09-21')
        self.assertEqual(str(shift.start_time), '09:00:00')
        self.assertEqual(str(shift.end_time), '17:00:00')
        self.assertEqual(shift.role, '店内掃除')

    def test_can_save_actual_work_without_changing_planned_time(self):
        staff = Staff.objects.create(name='佐藤')
        shift_type = ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        shift = Shift.objects.create(
            staff=staff,
            shift_type=shift_type,
            work_date='2026-09-21',
            start_time='09:00',
            end_time='17:00',
        )

        response = self.client.post(
            reverse('actual_work_edit', args=['2026-09-21']),
            {
                f'actual_start_{staff.pk}': '09:15',
                f'actual_end_{staff.pk}': '16:45',
            },
            follow=True,
        )

        shift.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(shift.start_time), '09:00:00')
        self.assertEqual(str(shift.end_time), '17:00:00')
        self.assertEqual(str(shift.actual_start_time), '09:15:00')
        self.assertEqual(str(shift.actual_end_time), '16:45:00')
        self.assertContains(response, '実働時間を保存しました。')

    def test_actual_work_edit_can_create_actual_only_shift(self):
        staff = Staff.objects.create(name='田中')

        response = self.client.post(
            reverse('actual_work_edit', args=['2026-09-21']),
            {
                f'actual_start_{staff.pk}': '10:00',
                f'actual_end_{staff.pk}': '15:00',
            },
            follow=True,
        )

        shift = Shift.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(shift.staff, staff)
        self.assertEqual(str(shift.work_date), '2026-09-21')
        self.assertIsNone(shift.start_time)
        self.assertIsNone(shift.end_time)
        self.assertEqual(str(shift.actual_start_time), '10:00:00')
        self.assertEqual(str(shift.actual_end_time), '15:00:00')

    def test_actual_work_requires_start_and_end(self):
        staff = Staff.objects.create(name='田中')

        response = self.client.post(
            reverse('actual_work_edit', args=['2026-09-21']),
            {
                f'actual_start_{staff.pk}': '10:00',
                f'actual_end_{staff.pk}': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Shift.objects.count(), 0)
        self.assertContains(response, '田中さんの開始時刻と終了時刻を両方入力してください。')

    def test_can_create_shift_type(self):
        response = self.client.post(
            reverse('shift_type_create'),
            {
                'code': 'B',
                'color': '#FFE4CC',
                'start_time': '17:00',
                'end_time': '22:00',
                'break_minutes': '45',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftType.objects.count(), 1)
        self.assertContains(response, '17:00-22:00')
        self.assertNotContains(response, '名称')
        self.assertEqual(str(ShiftType.objects.get()), 'B 17:00-22:00')
        self.assertEqual(ShiftType.objects.get().color, '#FFE4CC')
        self.assertEqual(ShiftType.objects.get().break_minutes, 45)

    def test_cannot_reuse_shift_type_color(self):
        ShiftType.objects.create(
            code='A',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )

        response = self.client.post(
            reverse('shift_type_create'),
            {
                'code': 'B',
                'color': '#FADADD',
                'start_time': '17:00',
                'end_time': '22:00',
                'break_minutes': '45',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftType.objects.count(), 1)
        self.assertContains(response, 'この色はすでに使用されています。')

    def test_can_create_day_off_shift_type(self):
        response = self.client.post(
            reverse('shift_type_create'),
            {
                'code': '休',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftType.objects.count(), 1)
        self.assertContains(response, '休')
        self.assertEqual(str(ShiftType.objects.get()), '休')

    def test_can_create_day_off_shift_without_time(self):
        staff = Staff.objects.create(name='山田')
        shift_type = ShiftType.objects.create(code='休')

        response = self.client.post(
            reverse('shift_create'),
            {
                'staff': staff.pk,
                'shift_type': shift_type.pk,
                'work_date': '2026-09-21',
            },
            follow=True,
        )

        shift = Shift.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(shift.start_time)
        self.assertIsNone(shift.end_time)

    def test_can_update_shift(self):
        staff = Staff.objects.create(name='鈴木')
        shift = Shift.objects.create(
            staff=staff,
            work_date='2026-09-21',
            start_time='09:00',
            end_time='17:00',
        )

        response = self.client.post(
            reverse('shift_update', args=[shift.pk]),
            {
                'staff': staff.pk,
                'work_date': '2026-09-22',
                'start_time': '10:00',
                'end_time': '18:00',
                'role': '銀行・トイレ掃除',
            },
            follow=True,
        )

        shift.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(shift.work_date), '2026-09-22')
        self.assertEqual(shift.role, '銀行・トイレ掃除')

    def test_can_delete_shift(self):
        staff = Staff.objects.create(name='高橋')
        shift = Shift.objects.create(
            staff=staff,
            work_date='2026-09-21',
            start_time='09:00',
            end_time='17:00',
        )

        response = self.client.post(
            reverse('shift_delete', args=[shift.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Shift.objects.count(), 0)


class MonthNavigationTests(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name='Test')
        self.shift = Shift.objects.create(
            staff=self.staff, work_date='2025-02-10',
            start_time='09:00', end_time='17:00',
        )
        self.table_url = reverse('shift_table') + '?month=2025-02'

    def test_delete_returns_to_shift_month_without_referrer(self):
        response = self.client.post(reverse('shift_delete', args=[self.shift.pk]))
        self.assertRedirects(response, self.table_url)
        self.assertFalse(Shift.objects.filter(pk=self.shift.pk).exists())

    def test_update_preserves_original_month_when_date_changes(self):
        response = self.client.post(reverse('shift_update', args=[self.shift.pk]), {
            'staff': self.staff.pk, 'work_date': '2025-03-10',
            'start_time': '09:00', 'end_time': '17:00',
        })
        self.assertRedirects(response, self.table_url)
        self.shift.refresh_from_db()
        self.assertEqual(str(self.shift.work_date), '2025-03-10')

    def test_create_returns_to_selected_month_after_validation_error(self):
        url = reverse('shift_create')
        response = self.client.post(url, {'month': '2025-02', 'staff': self.staff.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="month" value="2025-02"')
        response = self.client.post(url, {
            'month': '2025-02', 'staff': self.staff.pk, 'work_date': '2025-02-12',
            'start_time': '09:00', 'end_time': '17:00', 'next': 'https://example.com',
        })
        self.assertRedirects(response, self.table_url)

    def test_cancel_links_preserve_month(self):
        for name in ['shift_update', 'shift_delete']:
            response = self.client.get(reverse(name, args=[self.shift.pk]))
            self.assertContains(response, f'href="{self.table_url}"')
        response = self.client.get(reverse('shift_create') + '?date=2025-02-12')
        self.assertContains(response, f'href="{self.table_url}"')

    def test_salary_settings_preserve_month(self):
        url = reverse('staff_salary_settings', args=[self.staff.pk]) + '?month=2025-02'
        response = self.client.get(url)
        salary_url = reverse('salary_list') + '?month=2025-02'
        self.assertContains(response, f'href="{salary_url}"')
        response = self.client.post(url, {'hourly_wage': '1200'})
        self.assertRedirects(response, salary_url)
        response = self.client.post(reverse('salary_settings') + '?month=2025-02', {
            'action': 'create', 'name': 'Test', 'amount_type': 'fixed',
            'direction': 'subtract', 'fixed_amount': '100',
        })
        self.assertRedirects(response, reverse('salary_settings') + '?month=2025-02')


class ShiftPrintTests(TestCase):
    def test_print_sections_cover_month_once(self):
        Staff.objects.create(name='Print test')
        for month, length in [('2025-02', 28), ('2024-02', 29), ('2025-04', 30), ('2025-03', 31)]:
            with self.subTest(month=month):
                response = self.client.get(reverse('shift_table'), {'month': month})
                sections = response.context['print_sections']
                self.assertEqual([len(section['days']) for section in sections], [10, 10, length - 20])
                self.assertEqual(
                    [day['date'].day for section in sections for day in section['days']],
                    list(range(1, length + 1)),
                )
                self.assertContains(response, 'class="print-shift-table"', count=3)

    def test_print_header_and_shift_assignment(self):
        staff = Staff.objects.create(name='Print test')
        shift = Shift.objects.create(staff=staff, work_date='2025-03-21', start_time='09:00', end_time='17:00')
        response = self.client.get(reverse('shift_table'), {'month': '2025-03'})
        self.assertContains(response, '1(\u571f)')
        sections = response.context['print_sections']
        self.assertIsNone(sections[0]['rows'][0]['cells'][0])
        self.assertEqual(sections[2]['rows'][0]['cells'][0], shift)


class ActualDayOffTests(TestCase):
    def test_day_off_preserves_plan_and_excludes_pay_then_can_be_cleared(self):
        from .views import _actual_shift_work_minutes, _salary_shift_minutes
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        shift = Shift.objects.create(staff=staff, work_date='2025-03-01', start_time='09:00', end_time='17:00')
        url = reverse('actual_work_edit', args=['2025-03-01'])
        response = self.client.post(url, {f'actual_day_off_{staff.pk}': '1'}, follow=True)
        self.assertEqual(response.status_code, 200)
        shift.refresh_from_db()
        self.assertTrue(shift.actual_day_off)
        self.assertEqual(str(shift.start_time), '09:00:00')
        self.assertIsNone(shift.actual_start_time)
        self.assertEqual(_actual_shift_work_minutes(shift, 480), 0)
        self.assertEqual(_salary_shift_minutes(shift), 0)
        self.assertRedirects(response, reverse('shift_table') + '?month=2025-03')
        edit_response = self.client.get(url)
        self.assertContains(edit_response, 'aria-pressed="true"')
        self.assertIsNone(edit_response.context['rows'][0]['actual_start'])
        self.client.post(url, {
            f'actual_day_off_{staff.pk}': '0',
            f'actual_start_{staff.pk}': '10:00', f'actual_end_{staff.pk}': '16:00',
        })
        shift.refresh_from_db()
        self.assertFalse(shift.actual_day_off)
        self.assertEqual(_salary_shift_minutes(shift), 360)

    def test_day_off_is_not_saved_when_another_row_is_invalid(self):
        staff = Staff.objects.create(name='Test')
        other = Staff.objects.create(name='Other')
        shift = Shift.objects.create(staff=staff, work_date='2025-03-01', start_time='09:00', end_time='17:00')
        response = self.client.post(reverse('actual_work_edit', args=['2025-03-01']), {
            f'actual_day_off_{staff.pk}': '1', f'actual_start_{other.pk}': '09:00',
        })
        shift.refresh_from_db()
        self.assertFalse(shift.actual_day_off)
        self.assertContains(response, 'aria-pressed="true"')


class ActualTableTests(TestCase):
    def test_actual_display_and_print_use_registered_times_without_category(self):
        staff = Staff.objects.create(name='Test')
        shift_type = ShiftType.objects.create(code='A')
        shift = Shift.objects.create(
            staff=staff, shift_type=shift_type, work_date='2025-03-01',
            start_time='09:00', end_time='17:00', actual_start_time='10:00', actual_end_time='16:00',
        )
        response = self.client.get(reverse('shift_table'), {'month': '2025-03', 'view': 'actual'})
        self.assertContains(response, '10:00-16:00', count=2)
        self.assertNotContains(response, '09:00-17:00')
        self.assertNotContains(response, 'type-badge')
        self.assertContains(response, 'class="print-shift-table"', count=3)
        self.assertTrue(response.context['print_sections'][0]['rows'][0]['cells'][0].actual_differs_from_plan)
        self.assertContains(response, '?month=2025-04&view=actual')
        response = self.client.get(reverse('shift_table'), {'month': '2025-03'})
        self.assertContains(response, '09:00-17:00')
        self.assertNotContains(response, '10:00-16:00')

    def test_actual_difference_covers_unregistered_matching_changed_and_day_off(self):
        from datetime import time
        shift = Shift(start_time=time(9), end_time=time(17))
        self.assertEqual(shift.actual_display_label, '\u672a\u767b\u9332')
        self.assertFalse(shift.actual_differs_from_plan)
        shift.actual_start_time, shift.actual_end_time = time(9), time(17)
        self.assertFalse(shift.actual_differs_from_plan)
        self.assertEqual(shift.actual_change_class, '')
        shift.actual_end_time = time(16)
        self.assertTrue(shift.actual_differs_from_plan)
        self.assertEqual(shift.actual_change_class, 'actual-changed')
        shift.actual_day_off = True
        self.assertEqual(shift.actual_change_class, 'actual-changed-off')
        self.assertEqual(shift.actual_display_label, '\u4f11')
        self.assertTrue(shift.actual_differs_from_plan)
        shift.shift_type = ShiftType(code='\u4f11')
        self.assertFalse(shift.actual_differs_from_plan)
        shift.actual_day_off = False
        self.assertTrue(shift.actual_differs_from_plan)
        self.assertEqual(shift.actual_change_class, 'actual-changed-work')

    def test_actual_edit_returns_to_actual_table(self):
        staff = Staff.objects.create(name='Test')
        url = reverse('actual_work_edit', args=['2025-03-01']) + '?view=actual'
        response = self.client.post(url, {f'actual_day_off_{staff.pk}': '1'}, follow=True)
        self.assertRedirects(response, reverse('shift_table') + '?month=2025-03&view=actual')
        self.assertContains(response, reverse('shift_table') + '?month=2025-03&view=actual')


class HolidayWageTests(TestCase):
    def test_weekend_and_holidays_use_special_rate(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000, holiday_hourly_wage=1200)
        for day in [18, 19, 20, 21, 22, 23]:
            Shift.objects.create(staff=staff, work_date=f'2026-09-{day}', start_time='09:00', end_time='10:00')
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        self.assertEqual(response.context['rows'][0]['gross_amount'], '7,000\u5186')

    def test_missing_rate_falls_back_and_zero_is_respected(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        Shift.objects.create(staff=staff, work_date='2026-09-19', start_time='09:00', end_time='10:00')
        url = reverse('salary_list') + '?month=2026-09'
        self.assertEqual(self.client.get(url).context['rows'][0]['gross_amount'], '1,000\u5186')
        staff.holiday_hourly_wage = 0
        staff.save()
        self.assertEqual(self.client.get(url).context['rows'][0]['gross_amount'], '0\u5186')

    def test_both_settings_forms_save_and_validate_rate(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        for name in ['staff_update', 'staff_salary_settings']:
            url = reverse(name, args=[staff.pk])
            response = self.client.post(url, {'name': 'Test', 'hourly_wage': '1000', 'holiday_hourly_wage': '1400'})
            self.assertEqual(response.status_code, 302)
            staff.refresh_from_db()
            self.assertEqual(staff.holiday_hourly_wage, 1400)
            for invalid in ['-1', 'abc', '12.5']:
                response = self.client.post(url, {'name': 'Test', 'hourly_wage': '999', 'holiday_hourly_wage': invalid})
                self.assertEqual(response.status_code, 200)
                staff.refresh_from_db()
                self.assertEqual(staff.hourly_wage, 1000)
                self.assertEqual(staff.holiday_hourly_wage, 1400)

    def test_work_on_planned_day_off_is_paid_at_holiday_rate(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000, holiday_hourly_wage=1200)
        off = ShiftType.objects.create(code='\u4f11')
        Shift.objects.create(staff=staff, shift_type=off, work_date='2026-09-19', actual_start_time='09:00', actual_end_time='11:00')
        Shift.objects.create(staff=staff, work_date='2026-09-20', start_time='09:00', end_time='11:00', actual_day_off=True)
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        self.assertEqual(response.context['rows'][0]['gross_amount'], '2,400\u5186')


class PaidLeaveTests(TestCase):
    def test_monthly_leave_is_added_without_work_hours_and_is_isolated(self):
        from .models import MonthlyPaidLeave
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        url = reverse('staff_salary_settings', args=[staff.pk])
        response = self.client.post(url + '?month=2026-09', {
            'hourly_wage': '1200', 'paid_leave-days': '2', 'paid_leave-hours_per_day': '7.5',
        })
        self.assertEqual(response.status_code, 302)
        leave = MonthlyPaidLeave.objects.get()
        self.assertEqual(leave.amount, 18000)
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        self.assertEqual(response.context['rows'][0]['gross_amount'], '18,000\u5186')
        self.assertEqual(response.context['rows'][0]['work_duration'], '00.00h')
        response = self.client.get(reverse('salary_list'), {'month': '2026-10'})
        self.assertEqual(response.context['rows'][0]['gross_amount'], '0\u5186')
        self.client.post(url + '?month=2026-10', {
            'hourly_wage': '1200', 'paid_leave-days': '2', 'paid_leave-hours_per_day': '8',
        })
        leave.refresh_from_db()
        self.assertEqual(leave.amount, 18000)
        self.assertEqual(MonthlyPaidLeave.objects.count(), 2)
        self.client.post(url + '?month=2026-09', {
            'hourly_wage': '1200', 'paid_leave-days': '0', 'paid_leave-hours_per_day': '7.5',
        })
        self.assertEqual(MonthlyPaidLeave.objects.count(), 2)
        leave.refresh_from_db()
        self.assertEqual(leave.amount, 0)

    def test_invalid_leave_does_not_save_wages(self):
        from .models import MonthlyPaidLeave
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        url = reverse('staff_salary_settings', args=[staff.pk]) + '?month=2026-09'
        for days, hours in [('-1', '8'), ('32', '8'), ('1', '25'), ('1', '0'), ('abc', '8'), ('1.001', '8')]:
            with self.subTest(days=days, hours=hours):
                response = self.client.post(url, {
                    'hourly_wage': '999', 'paid_leave-days': days, 'paid_leave-hours_per_day': hours,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['paid_leave_form'].errors)
                staff.refresh_from_db()
                self.assertEqual(staff.hourly_wage, 1200)
                self.assertFalse(MonthlyPaidLeave.objects.exists())


class WageHistoryTests(TestCase):
    def test_effective_month_preserves_past_pay_and_paid_leave(self):
        from datetime import date
        from .models import MonthlyPaidLeave, StaffWageHistory
        staff = Staff.objects.create(name='Test', hourly_wage=1000, holiday_hourly_wage=1200)
        for month in [9, 10, 11]:
            Shift.objects.create(staff=staff, work_date=date(2026, month, 15), start_time='09:00', end_time='10:00')
            MonthlyPaidLeave.objects.create(staff=staff, month=date(2026, month, 1), days=1, hours_per_day=2)
        url = reverse('staff_salary_settings', args=[staff.pk]) + '?month=2026-09'
        self.client.post(url, {'hourly_wage': '1500', 'holiday_hourly_wage': '1800', 'wage_effective_month': '2026-10'})
        staff.refresh_from_db()
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1000, 1200))
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1500, 1800))
        for month, expected in [('2026-09', '3,000'), ('2026-10', '4,500'), ('2026-11', '4,800')]:
            response = self.client.get(reverse('salary_list'), {'month': month})
            self.assertEqual(response.context['rows'][0]['gross_amount'], expected + '\u5186')
        self.client.post(url, {'hourly_wage': '1600', 'holiday_hourly_wage': '1900', 'wage_effective_month': '2026-10'})
        self.assertEqual(StaffWageHistory.objects.filter(staff=staff).count(), 2)
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1600, 1900))
        self.client.post(url, {'hourly_wage': '1100', 'holiday_hourly_wage': '', 'wage_effective_month': '2026-08'})
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1100, None))
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1600, 1900))

    def test_invalid_month_does_not_save(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        for name in ['staff_salary_settings', 'staff_update']:
            response = self.client.post(reverse(name, args=[staff.pk]), {
                'name': 'Test', 'hourly_wage': '2000', 'wage_effective_month': '2026-13',
            })
            self.assertEqual(response.status_code, 200)
            staff.refresh_from_db()
            self.assertEqual(staff.hourly_wage, 1000)
            self.assertFalse(staff.wage_history.exists())

    def test_staff_edit_also_preserves_previous_wage(self):
        from datetime import date
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        self.client.post(reverse('staff_update', args=[staff.pk]), {
            'name': 'Test', 'hourly_wage': '1300', 'wage_effective_month': '2026-10',
        })
        staff.refresh_from_db()
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1000, None))
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1300, None))


class WagePeriodTests(TestCase):
    def test_multiple_periods_save_and_reload(self):
        from datetime import date
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        url = reverse('staff_salary_settings', args=[staff.pk]) + '?month=2026-09'
        data = {
            'wages-TOTAL_FORMS': '2', 'wages-INITIAL_FORMS': '1',
            'wages-0-effective_month': '2026-09', 'wages-0-hourly_wage': '1100', 'wages-0-holiday_hourly_wage': '',
            'wages-1-effective_month': '2026-10', 'wages-1-hourly_wage': '1200', 'wages-1-holiday_hourly_wage': '1500',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(staff.wages_for_month(date(2026, 8, 1)), (1000, None))
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1100, None))
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1200, 1500))
        response = self.client.get(url)
        self.assertEqual(len(response.context['wage_periods'].forms), 2)
        self.assertContains(response, 'data-add-wage-period')
        data['wages-INITIAL_FORMS'] = '2'
        data['wages-0-hourly_wage'] = '1150'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1150, None))

    def test_duplicate_months_and_invalid_wages_do_not_save(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        url = reverse('staff_salary_settings', args=[staff.pk]) + '?month=2026-09'
        data = {
            'wages-TOTAL_FORMS': '2', 'wages-INITIAL_FORMS': '1',
            'wages-0-effective_month': '2026-09', 'wages-0-hourly_wage': '1100',
            'wages-1-effective_month': '2026-09', 'wages-1-hourly_wage': '1200',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['wage_periods'].non_form_errors())
        self.assertFalse(staff.wage_history.exists())
        data['wages-1-effective_month'] = '2026-10'
        data['wages-1-hourly_wage'] = '-1'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['wage_periods'].errors[1])
        self.assertFalse(staff.wage_history.exists())


class StaffWagePeriodTests(TestCase):
    def test_staff_edit_saves_periods_shared_with_salary_settings(self):
        from datetime import date
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        url = reverse('staff_update', args=[staff.pk])
        response = self.client.get(url)
        self.assertContains(response, 'data-add-wage-period')
        data = {
            'name': 'Updated', 'wages-TOTAL_FORMS': '2', 'wages-INITIAL_FORMS': '1',
            'wages-0-effective_month': '2026-09', 'wages-0-hourly_wage': '1100',
            'wages-1-effective_month': '2026-10', 'wages-1-hourly_wage': '1200',
            'wages-1-holiday_hourly_wage': '1500',
        }
        self.assertRedirects(self.client.post(url, data), reverse('staff_list'))
        staff.refresh_from_db()
        self.assertEqual(staff.name, 'Updated')
        self.assertEqual(staff.wages_for_month(date(2026, 8, 1)), (1000, None))
        self.assertEqual(staff.wages_for_month(date(2026, 9, 1)), (1100, None))
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1200, 1500))
        response = self.client.get(reverse('staff_salary_settings', args=[staff.pk]))
        self.assertEqual(len(response.context['wage_periods'].forms), 2)
        data['wages-INITIAL_FORMS'] = '2'
        data['wages-1-hourly_wage'] = '-1'
        data['name'] = 'Invalid'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['wage_periods'].errors[1])
        staff.refresh_from_db()
        self.assertEqual(staff.name, 'Updated')
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1200, 1500))


class StaffPaidLeaveHoursTests(TestCase):
    def test_staff_hours_default_for_new_month_and_preserve_saved_month(self):
        from datetime import date
        from decimal import Decimal
        from .models import MonthlyPaidLeave
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        url = reverse('staff_update', args=[staff.pk])
        self.assertEqual(self.client.post(url, {'name': 'Test', 'hourly_wage': '1200', 'paid_leave_hours_per_day': '7.5'}).status_code, 302)
        staff.refresh_from_db()
        self.assertEqual(staff.paid_leave_hours_per_day, Decimal('7.5'))
        MonthlyPaidLeave.objects.create(staff=staff, month=date(2026, 9, 1), days=1, hours_per_day=6)
        settings = reverse('staff_salary_settings', args=[staff.pk])
        for month, hours in [('2026-09', 6), ('2026-10', Decimal('7.5'))]:
            response = self.client.get(settings, {'month': month})
            self.assertEqual(response.context['paid_leave_form'].initial['hours_per_day'], hours)

    def test_invalid_staff_hours_rejected(self):
        staff = Staff.objects.create(name='Test', paid_leave_hours_per_day=8)
        for value in ['-1', '25', 'abc', '7.555', 'NaN']:
            response = self.client.post(reverse('staff_update', args=[staff.pk]), {
                'name': 'Changed', 'paid_leave_hours_per_day': value,
            })
            self.assertEqual(response.status_code, 200)
            staff.refresh_from_db()
            self.assertEqual(staff.name, 'Test')
            self.assertEqual(staff.paid_leave_hours_per_day, 8)


class WageDeleteAndLeaveIntegerTests(TestCase):
    def test_change_month_and_delete_periods(self):
        from datetime import date
        from .models import StaffWageHistory
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        StaffWageHistory.objects.create(staff=staff, effective_month=date.min, hourly_wage=1000)
        StaffWageHistory.objects.create(staff=staff, effective_month=date(2026, 9, 1), hourly_wage=1200)
        StaffWageHistory.objects.create(staff=staff, effective_month=date(2026, 10, 1), hourly_wage=1400)
        data = {'name': 'Test', 'wages-TOTAL_FORMS': '2', 'wages-INITIAL_FORMS': '2',
                'wages-0-effective_month': '2026-08', 'wages-0-hourly_wage': '1300',
                'wages-1-effective_month': '2026-10', 'wages-1-hourly_wage': '1400', 'wages-1-DELETE': 'on'}
        response = self.client.post(reverse('staff_update', args=[staff.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(staff.wage_history.filter(effective_month=date(2026, 9, 1)).exists())
        self.assertFalse(staff.wage_history.filter(effective_month=date(2026, 10, 1)).exists())
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1300, None))
        data.update({'wages-TOTAL_FORMS': '1', 'wages-INITIAL_FORMS': '1', 'wages-0-DELETE': 'on'})
        response = self.client.post(reverse('staff_salary_settings', args=[staff.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(staff.wages_for_month(date(2026, 10, 1)), (1000, None))

    def test_fractional_paid_leave_is_rejected(self):
        from .forms import MonthlyPaidLeaveForm
        for days in ['0.5', '1.5', '-1']:
            form = MonthlyPaidLeaveForm(data={'days': days, 'hours_per_day': '7.5'})
            self.assertFalse(form.is_valid())
            self.assertIn('days', form.errors)
        form = MonthlyPaidLeaveForm(data={'days': '2', 'hours_per_day': '7.5'})
        self.assertTrue(form.is_valid())


class ActualBreakTests(TestCase):
    def test_break_override_changes_work_and_pay_without_changing_plan(self):
        from .views import _actual_shift_work_minutes, _salary_shift_minutes
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        category = ShiftType.objects.create(code='A', break_minutes=60)
        shift = Shift.objects.create(staff=staff, shift_type=category, work_date='2026-09-18', start_time='09:00', end_time='17:00')
        url = reverse('actual_work_edit', args=['2026-09-18'])
        for value, expected in [('30', 450), ('0', 480), ('', 420)]:
            response = self.client.post(url, {f'actual_start_{staff.pk}': '09:00', f'actual_end_{staff.pk}': '17:00', f'actual_break_{staff.pk}': value})
            self.assertEqual(response.status_code, 302)
            shift.refresh_from_db()
            self.assertEqual(_actual_shift_work_minutes(shift, 420), expected)
            self.assertEqual(_salary_shift_minutes(shift), expected)
            self.assertEqual(shift.planned_break_minutes, 60)
            self.assertEqual(shift.actual_differs_from_plan, value != '')
        response = self.client.get(url)
        self.assertEqual(response.context['rows'][0]['actual_break'], 60)

    def test_invalid_break_does_not_save(self):
        staff = Staff.objects.create(name='Test')
        shift = Shift.objects.create(staff=staff, work_date='2026-09-18', start_time='09:00', end_time='17:00')
        for value in ['-1', '481', '1.5', 'abc']:
            response = self.client.post(reverse('actual_work_edit', args=['2026-09-18']), {
                f'actual_start_{staff.pk}': '09:00', f'actual_end_{staff.pk}': '17:00', f'actual_break_{staff.pk}': value,
            })
            self.assertEqual(response.status_code, 200)
            shift.refresh_from_db()
            self.assertIsNone(shift.actual_start_time)
            self.assertIsNone(shift.actual_break_minutes)


class OvertimeTests(TestCase):
    def test_only_time_after_category_end_plus_fifteen_counts(self):
        from datetime import date, time
        category = ShiftType(code='A', end_time=time(17))
        self.assertEqual(category.overtime_start_label, '17:15')
        shift = Shift(shift_type=category, work_date=date(2026, 9, 18), end_time=time(16), actual_start_time=time(9))
        for end, expected in [(time(17), 0), (time(17, 14), 0), (time(17, 15), 0), (time(17, 16), 1), (time(17, 30), 15)]:
            shift.actual_end_time = end
            self.assertEqual(shift.overtime_minutes, expected)
        shift.actual_day_off = True
        self.assertEqual(shift.overtime_minutes, 0)
        shift.actual_day_off = False
        shift.actual_start_time = time(17, 20)
        self.assertEqual(shift.overtime_minutes, 10)
        shift.shift_type = None
        self.assertEqual(shift.overtime_minutes, 0)

    def test_no_overtime_for_unregistered_or_day_off(self):
        from datetime import date, time
        shift = Shift(work_date=date(2026, 9, 18), shift_type=ShiftType(code='A', end_time=time(17)))
        self.assertEqual(shift.overtime_minutes, 0)
        shift.shift_type = ShiftType(code='\u4f11')
        self.assertEqual(shift.shift_type.overtime_start_label, '-')
        self.assertEqual(shift.overtime_minutes, 0)
        category = ShiftType(code='A', end_time=time(23, 50))
        self.assertEqual(category.overtime_start_label, '\u7fcc\u65e5 00:05')


class PayrollRoundingTests(TestCase):
    def test_payable_overtime_boundaries_and_early_start(self):
        from datetime import date, time
        from .views import _salary_shift_minutes, _actual_shift_work_minutes
        category = ShiftType(code='A', start_time=time(9), end_time=time(17), break_minutes=60)
        shift = Shift(shift_type=category, work_date=date(2026, 9, 18), start_time=time(9), end_time=time(17), actual_start_time=time(8, 30))
        for end, minutes in [(time(16, 30), 390), (time(17), 420), (time(17, 14), 420), (time(17, 15), 420), (time(17, 16), 435), (time(17, 30), 435), (time(17, 31), 450), (time(17, 45), 450), (time(17, 46), 465)]:
            with self.subTest(end=end):
                shift.actual_end_time = end
                self.assertEqual(_salary_shift_minutes(shift), minutes)
        self.assertEqual(_actual_shift_work_minutes(shift, 0), 496)
        shift.actual_start_time = time(9, 30)
        shift.actual_end_time = time(17, 16)
        self.assertEqual(_salary_shift_minutes(shift), 405)
        shift.actual_break_minutes = 30
        self.assertEqual(_salary_shift_minutes(shift), 435)
        shift.actual_day_off = True
        self.assertEqual(_salary_shift_minutes(shift), 0)

    def test_no_schedule_uses_recorded_work_and_schedule_fallback(self):
        from datetime import date, time
        from .views import _salary_shift_minutes
        shift = Shift(work_date=date(2026, 9, 18), actual_start_time=time(9), actual_end_time=time(17, 16), actual_break_minutes=30)
        self.assertEqual(_salary_shift_minutes(shift), 466)
        shift.start_time, shift.end_time = time(9), time(17)
        self.assertEqual(_salary_shift_minutes(shift), 465)
        shift.actual_start_time, shift.actual_end_time = None, None
        self.assertEqual(_salary_shift_minutes(shift), 480)


class LeaveTypeTests(TestCase):
    def test_default_leave_types_and_separate_forms(self):
        expected = {'\u5e0c\u671b\u4f11': '#DC2626', '\u6307\u5b9a\u4f11': '#222222', '\u305d\u306e\u4ed6': '#F97316'}
        for code, color in expected.items():
            leave = ShiftType.objects.get(code=code)
            self.assertTrue(leave.is_leave)
            self.assertEqual(leave.color, color)
        response = self.client.get(reverse('shift_type_create'), {'kind': 'leave'})
        self.assertTrue(response.context['is_leave'])
        self.assertContains(response, '#808080')
        self.assertNotIn(('A', 'A'), response.context['codes'])
        response = self.client.get(reverse('shift_type_create'), {'kind': 'work'})
        self.assertFalse(response.context['is_leave'])
        self.assertEqual(len(response.context['codes']), 26)

    def test_leave_saves_without_times_and_renders_color_and_name(self):
        from .views import _salary_shift_minutes
        staff = Staff.objects.create(name='Test')
        leave = ShiftType.objects.get(code='\u5e0c\u671b\u4f11')
        response = self.client.post(reverse('shift_create'), {
            'staff': staff.pk, 'work_date': '2026-09-18', 'shift_type': leave.pk,
        })
        self.assertEqual(response.status_code, 302)
        shift = Shift.objects.get(staff=staff)
        self.assertIsNone(shift.start_time)
        self.assertEqual(_salary_shift_minutes(shift), 0)
        response = self.client.get(reverse('shift_table'), {'month': '2026-09'})
        self.assertContains(response, leave.code)
        self.assertContains(response, 'background-color: #e8e8e8; color: #DC2626;')
        response = self.client.post(reverse('shift_type_update', args=[leave.pk]), {
            'kind': 'leave', 'code': leave.code, 'color': '#808080',
        })
        self.assertEqual(response.status_code, 302)
        leave.refresh_from_db()
        self.assertEqual(leave.color, '#808080')
        self.assertIsNone(leave.end_time)

    def test_leave_bulk_save_and_actual_work(self):
        from datetime import time
        from .views import _salary_shift_minutes
        staff = Staff.objects.create(name='Test')
        leave = ShiftType.objects.get(code='\u6307\u5b9a\u4f11')
        response = self.client.post(reverse('shift_table') + '?month=2026-09&mode=edit', {
            f'shift_type_{staff.pk}_20260918': str(leave.pk),
        })
        self.assertEqual(response.status_code, 302)
        shift = Shift.objects.get(staff=staff)
        self.assertEqual(shift.shift_type, leave)
        self.assertIsNone(shift.start_time)
        shift.actual_start_time, shift.actual_end_time = time(9), time(10)
        self.assertEqual(shift.actual_change_class, 'actual-changed-work')
        self.assertEqual(_salary_shift_minutes(shift), 60)


class SalaryHoursDisplayTests(TestCase):
    def test_display_uses_payable_hours_excluding_discarded_time(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        category = ShiftType.objects.create(code='A', start_time='09:00', end_time='17:00', break_minutes=60)
        Shift.objects.create(staff=staff, shift_type=category, work_date='2026-09-18',
                             start_time='09:00', end_time='17:00', actual_start_time='08:30', actual_end_time='17:15')
        Shift.objects.create(staff=staff, shift_type=category, work_date='2026-09-19',
                             start_time='09:00', end_time='17:00', actual_start_time='08:30', actual_end_time='17:16')
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        row = response.context['rows'][0]
        self.assertEqual(row['weekday_duration'], '07.00h')
        self.assertEqual(row['holiday_duration'], '07.25h')
        self.assertEqual(row['work_duration'], '14.25h')
        self.assertEqual(response.context['total_duration'], '14.25h')
        self.assertEqual(row['gross_amount'], '17,100\u5186')


class ActualShiftTypeTests(TestCase):
    def test_actual_category_changes_independently_and_controls_payroll(self):
        from .views import _salary_shift_minutes
        staff = Staff.objects.create(name='Test')
        planned = ShiftType.objects.create(code='A', start_time='09:00', end_time='17:00', break_minutes=60)
        actual = ShiftType.objects.create(code='B', start_time='10:00', end_time='18:00', break_minutes=30)
        shift = Shift.objects.create(staff=staff, shift_type=planned, work_date='2026-09-18', start_time='09:00', end_time='17:00')
        url = reverse('actual_work_edit', args=['2026-09-18'])
        response = self.client.post(url, {
            f'actual_type_{staff.pk}': actual.pk, f'actual_start_{staff.pk}': '09:30',
            f'actual_end_{staff.pk}': '18:16', f'actual_break_{staff.pk}': '',
        })
        self.assertEqual(response.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.shift_type, planned)
        self.assertEqual(str(shift.start_time), '09:00:00')
        self.assertEqual(str(shift.end_time), '17:00:00')
        self.assertEqual(shift.actual_shift_type, actual)
        self.assertEqual(shift.effective_break_minutes, 30)
        self.assertEqual(shift.overtime_minutes, 1)
        self.assertEqual(_salary_shift_minutes(shift), 465)
        self.assertTrue(shift.actual_differs_from_plan)
        response = self.client.get(url)
        self.assertEqual(response.context['rows'][0]['actual_type_id'], str(actual.pk))
        self.client.post(url, {f'actual_type_{staff.pk}': '', f'actual_start_{staff.pk}': '09:00',
                               f'actual_end_{staff.pk}': '17:00', f'actual_break_{staff.pk}': '60'})
        shift.refresh_from_db()
        self.assertIsNone(shift.actual_shift_type)
        self.assertFalse(shift.actual_differs_from_plan)

    def test_leave_category_and_invalid_category(self):
        staff = Staff.objects.create(name='Test')
        planned = ShiftType.objects.create(code='A', start_time='09:00', end_time='17:00')
        leave = ShiftType.objects.get(code='\u5e0c\u671b\u4f11')
        shift = Shift.objects.create(staff=staff, shift_type=planned, work_date='2026-09-18', start_time='09:00', end_time='17:00')
        url = reverse('actual_work_edit', args=['2026-09-18'])
        self.assertEqual(self.client.post(url, {f'actual_type_{staff.pk}': leave.pk}).status_code, 302)
        shift.refresh_from_db()
        self.assertTrue(shift.actual_day_off)
        self.assertEqual(shift.actual_display_label, leave.code)
        self.assertEqual(shift.shift_type, planned)
        self.assertIsNone(shift.actual_start_time)
        self.assertEqual(self.client.post(url, {f'actual_type_{staff.pk}': '999999'}).status_code, 200)
        shift.refresh_from_db()
        self.assertEqual(shift.actual_shift_type, leave)


class SalaryDetailTests(TestCase):
    def test_saved_schedule_takes_priority_over_category_defaults(self):
        from datetime import date, time
        from .views import _salary_shift_minutes, _format_salary_hours
        shift = Shift(work_date=date(2026, 9, 25),
                      shift_type=ShiftType(code='A', start_time=time(9, 45), end_time=time(19, 30)),
                      start_time=time(9, 45), end_time=time(15, 30),
                      actual_start_time=time(9, 38), actual_end_time=time(15, 31), actual_break_minutes=30)
        self.assertEqual(_salary_shift_minutes(shift), 315)
        self.assertEqual(_format_salary_hours(_salary_shift_minutes(shift)), '05.25h')

    def test_daily_detail_reconciles_with_payroll_and_distinguishes_fallback(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        other = Staff.objects.create(name='Other')
        category = ShiftType.objects.create(code='A', start_time='09:00', end_time='17:00', break_minutes=60)
        for day in [18, 19, 20]:
            Shift.objects.create(staff=staff, shift_type=category, work_date=f'2026-09-{day}',
                start_time='09:00', end_time='17:00',
                actual_start_time='08:30' if day == 18 else None,
                actual_end_time='17:16' if day == 18 else None, actual_day_off=day == 20)
        Shift.objects.create(staff=other, work_date='2026-09-18', start_time='12:00', end_time='13:00')
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        row = next(row for row in response.context['rows'] if row['staff'] == staff)
        details = row['daily_salary']
        self.assertEqual([day['date'].day for day in details], [18, 19, 20])
        self.assertEqual([day['minutes'] for day in details], [435, 420, 0])
        self.assertEqual(row['work_duration'], '14.25h')
        self.assertEqual(details[1]['source'], '\u4e88\u5b9a\uff08\u5b9f\u50cd\u672a\u767b\u9332\uff09')
        self.assertIsNone(details[2]['start'])
        self.assertContains(response, f'data-salary-detail="salary-detail-{staff.pk}"')
        self.assertContains(response, '08:30\u301c17:16')


class MonthlyAdjustmentTests(TestCase):
    def test_personal_adjustments_are_month_specific(self):
        from datetime import date
        staff = Staff.objects.create(name='Test', hourly_wage=1000)
        deduction = SalaryDeduction.objects.create(name='Adjustment', amount_type='variable', direction='add')
        StaffSalaryDeduction.objects.create(staff=staff, deduction=deduction, amount=100, is_active=True)
        url = reverse('staff_salary_settings', args=[staff.pk])
        for month, amount, active in [('2026-08', '300', True), ('2026-09', '500', False)]:
            data = {'hourly_wage': '1000', f'deduction_amount_{deduction.pk}': amount}
            if active:
                data[f'deduction_active_{deduction.pk}'] = 'on'
            self.assertEqual(self.client.post(url + '?month=' + month, data).status_code, 302)
        self.assertEqual(StaffSalaryDeduction.objects.get(staff=staff, deduction=deduction).amount, 100)
        for month, expected in [('2026-08', '+300'), ('2026-09', '\u00b10'), ('2026-10', '+100')]:
            row = self.client.get(reverse('salary_list'), {'month': month}).context['rows'][0]
            self.assertEqual(row['adjustment_amount'], expected + '\u5186')
        rows = self.client.get(url, {'month': '2026-08'}).context['rows']
        self.assertEqual(rows[0]['amount'], 300)
        self.assertTrue(rows[0]['is_active'])
        self.client.post(url + '?month=2026-08', {'hourly_wage': '1000', f'deduction_amount_{deduction.pk}': '400', f'deduction_active_{deduction.pk}': 'on'})
        self.assertEqual(MonthlyStaffSalaryDeduction.objects.count(), 2)
        self.assertEqual(MonthlyStaffSalaryDeduction.objects.get(month=date(2026, 9, 1)).amount, 500)

    def test_saved_fixed_amount_survives_global_amount_change(self):
        staff = Staff.objects.create(name='Test')
        deduction = SalaryDeduction.objects.create(name='Fixed', amount_type='fixed', fixed_amount=200)
        self.client.post(reverse('staff_salary_settings', args=[staff.pk]) + '?month=2026-08', {
            f'deduction_active_{deduction.pk}': 'on',
        })
        deduction.fixed_amount = 900
        deduction.save()
        for month, expected in [('2026-08', '-200'), ('2026-09', '-900')]:
            row = self.client.get(reverse('salary_list'), {'month': month}).context['rows'][0]
            self.assertEqual(row['adjustment_amount'], expected + '\u5186')


class SalaryVisibilityTests(TestCase):
    def test_staff_can_be_hidden_and_restored_without_losing_shifts(self):
        staff = Staff.objects.create(name='Test', hourly_wage=1200)
        shift = Shift.objects.create(staff=staff, work_date='2026-09-18', start_time='09:00', end_time='10:00')
        url = reverse('staff_salary_visibility', args=[staff.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {'show_in_salary': '0', 'year': '2026'})
        self.assertRedirects(response, reverse('staff_list') + '?year=2026')
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        self.assertEqual(response.context['rows'], [])
        self.assertEqual(response.context['total_gross_amount'], '0\u5186')
        self.assertTrue(Shift.objects.filter(pk=shift.pk).exists())
        self.assertContains(self.client.get(reverse('staff_list')), 'Test')
        self.assertContains(self.client.get(reverse('shift_table'), {'month': '2026-09'}), 'Test')
        self.client.post(url, {'show_in_salary': '1', 'year': '2026'})
        response = self.client.get(reverse('salary_list'), {'month': '2026-09'})
        self.assertEqual(len(response.context['rows']), 1)
        self.assertEqual(response.context['total_gross_amount'], '1,200\u5186')
