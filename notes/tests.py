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
            name='早番',
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
            name='早番',
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
            name='早番',
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
            name='早番',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )
        holiday_type = ShiftType.objects.create(code='休', name='休み')
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
            name='早番',
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
            name='早番',
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
            name='早番',
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
                'name': '遅番',
                'color': '#FFE4CC',
                'start_time': '17:00',
                'end_time': '22:00',
                'break_minutes': '45',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftType.objects.count(), 1)
        self.assertContains(response, '遅番')
        self.assertEqual(ShiftType.objects.get().color, '#FFE4CC')
        self.assertEqual(ShiftType.objects.get().break_minutes, 45)

    def test_cannot_reuse_shift_type_color(self):
        ShiftType.objects.create(
            code='A',
            name='早番',
            color='#FADADD',
            start_time='09:00',
            end_time='17:00',
            break_minutes=60,
        )

        response = self.client.post(
            reverse('shift_type_create'),
            {
                'code': 'B',
                'name': '遅番',
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
                'name': '休み',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftType.objects.count(), 1)
        self.assertContains(response, '休み')

    def test_can_create_day_off_shift_without_time(self):
        staff = Staff.objects.create(name='山田')
        shift_type = ShiftType.objects.create(code='休', name='休み')

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
