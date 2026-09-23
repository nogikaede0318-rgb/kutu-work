from django.test import TestCase
from django.urls import reverse

from .models import SalaryDeduction, Shift, ShiftType, Staff, StaffSalaryDeduction


class ShiftViewTests(TestCase):
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
        self.assertContains(response, '8時間')
        self.assertContains(response, '9,600円')

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
        staff_deduction = StaffSalaryDeduction.objects.get(staff=staff, deduction=deduction)
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
        shift.actual_end_time = time(16)
        self.assertTrue(shift.actual_differs_from_plan)
        shift.actual_day_off = True
        self.assertEqual(shift.actual_display_label, '\u4f11')
        self.assertTrue(shift.actual_differs_from_plan)
        shift.shift_type = ShiftType(code='\u4f11')
        self.assertFalse(shift.actual_differs_from_plan)
        shift.actual_day_off = False
        self.assertTrue(shift.actual_differs_from_plan)

    def test_actual_edit_returns_to_actual_table(self):
        staff = Staff.objects.create(name='Test')
        url = reverse('actual_work_edit', args=['2025-03-01']) + '?view=actual'
        response = self.client.post(url, {f'actual_day_off_{staff.pk}': '1'}, follow=True)
        self.assertRedirects(response, reverse('shift_table') + '?month=2025-03&view=actual')
        self.assertContains(response, reverse('shift_table') + '?month=2025-03&view=actual')
