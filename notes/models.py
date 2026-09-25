from datetime import datetime, timedelta

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


LEAVE_TYPE_CODES = [('休', '休'), ('希望休', '希望休'), ('指定休', '指定休'), ('その他', 'その他')]
WORK_TYPE_CODES = [(chr(code), chr(code)) for code in range(ord('A'), ord('Z') + 1)]
SHIFT_TYPE_CODES = LEAVE_TYPE_CODES + WORK_TYPE_CODES
LEAVE_TYPE_COLORS = [('#DC2626', '赤'), ('#222222', '黒'), ('#808080', 'グレー'), ('#F97316', 'オレンジ')]

SHIFT_TYPE_COLORS = [
    ('#FADADD', '赤系1'),
    ('#FFDDD2', '赤系2'),
    ('#FFE4CC', '橙系1'),
    ('#FBE7C6', '橙系2'),
    ('#F6E5D5', '橙系3'),
    ('#FFF3B0', '黄系1'),
    ('#FDFFB6', '黄系2'),
    ('#E9F5DB', '黄緑系1'),
    ('#E2F0CB', '黄緑系2'),
    ('#D9F2D0', '緑系1'),
    ('#D8F3DC', '緑系2'),
    ('#CAFFBF', '緑系3'),
    ('#C9F0DD', '青緑系1'),
    ('#CDEFE6', '青緑系2'),
    ('#CFE8E8', '水色系1'),
    ('#D7EEF8', '水色系2'),
    ('#BDE0FE', '水色系3'),
    ('#D2E3FC', '青系1'),
    ('#DDE7FF', '青系2'),
    ('#BDB2FF', '紫系1'),
    ('#CDB4DB', '紫系2'),
    ('#E4D7FF', '紫系3'),
    ('#E8DDF7', '紫系4'),
    ('#F6DDF0', '桃系1'),
    ('#FFD6E7', '桃系2'),
    ('#FFC8DD', '桃系3'),
]
SHIFT_TYPE_COLOR_VALUES = [color for color, _label in SHIFT_TYPE_COLORS]
BREAK_MINUTE_CHOICES = [
    (0, '0分'),
    (30, '30分'),
    (45, '45分'),
    (60, '60分'),
]
DEDUCTION_AMOUNT_TYPES = [
    ('fixed', '固定'),
    ('variable', '変動'),
]
SALARY_AMOUNT_DIRECTIONS = [
    ('subtract', '−'),
    ('add', '+'),
]


class Staff(models.Model):
    show_in_salary = models.BooleanField('給料一覧に表示', default=True)
    management_number = models.CharField('管理番号', max_length=2, unique=True, blank=True, null=True)
    name = models.CharField('名前', max_length=80, unique=True)
    hourly_wage = models.PositiveIntegerField('平日時給', default=0)
    holiday_hourly_wage = models.PositiveIntegerField('土日祝日時給', blank=True, null=True)
    paid_leave_hours_per_day = models.DecimalField(
        '有給1日あたりの時間', max_digits=4, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

    class Meta:
        ordering = [models.F('management_number').asc(nulls_last=True), 'name']
        verbose_name = 'スタッフ'
        verbose_name_plural = 'スタッフ'

    def __str__(self):
        return self.name

    def wages_for_month(self, month):
        wage = self.wage_history.filter(effective_month__lte=month.replace(day=1)).order_by('-effective_month').first()
        weekday = wage.hourly_wage if wage else self.hourly_wage
        holiday = wage.holiday_hourly_wage if wage else self.holiday_hourly_wage
        return weekday, holiday


class StaffWageHistory(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='wage_history')
    effective_month = models.DateField('適用開始月')
    hourly_wage = models.PositiveIntegerField('平日時給')
    holiday_hourly_wage = models.PositiveIntegerField('土日祝日時給', blank=True, null=True)

    class Meta:
        ordering = ['-effective_month']
        constraints = [models.UniqueConstraint(fields=['staff', 'effective_month'], name='unique_staff_wage_month')]


class MonthlyPaidLeave(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='monthly_paid_leave')
    month = models.DateField('対象月')
    days = models.DecimalField('有給日数', max_digits=4, decimal_places=2, default=0,
                               validators=[MinValueValidator(0), MaxValueValidator(31)])
    hours_per_day = models.DecimalField('1日あたりの時間', max_digits=4, decimal_places=2, default=0,
                                        validators=[MinValueValidator(0), MaxValueValidator(24)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['staff', 'month'], name='unique_staff_paid_leave_month')]

    @property
    def amount(self):
        weekday_wage, _ = self.staff.wages_for_month(self.month)
        return int(weekday_wage * self.hours_per_day * self.days)


class SalaryDeduction(models.Model):
    name = models.CharField('項目名', max_length=80, unique=True)
    amount_type = models.CharField('金額区分', max_length=10, choices=DEDUCTION_AMOUNT_TYPES, default='fixed')
    direction = models.CharField('加減区分', max_length=10, choices=SALARY_AMOUNT_DIRECTIONS, default='subtract')
    fixed_amount = models.PositiveIntegerField('固定金額', default=0)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = '差引項目'
        verbose_name_plural = '差引項目'

    def __str__(self):
        return self.name


class StaffSalaryDeduction(models.Model):
    reset_from_month = models.DateField('リセット開始月', blank=True, null=True)

    def for_month(self, month):
        if self.reset_from_month and month >= self.reset_from_month:
            return MonthlyStaffSalaryDeduction(
                staff_id=self.staff_id, deduction_id=self.deduction_id,
                month=month, amount=0, is_active=False,
            )
        return self

    staff = models.ForeignKey(Staff, verbose_name='スタッフ', on_delete=models.CASCADE, related_name='salary_deductions')
    deduction = models.ForeignKey(
        SalaryDeduction,
        verbose_name='差引項目',
        on_delete=models.CASCADE,
        related_name='staff_amounts',
    )
    amount = models.PositiveIntegerField('金額', default=0)
    is_active = models.BooleanField('適用', default=True)

    class Meta:
        ordering = ['deduction__name', 'staff__management_number', 'staff__name']
        constraints = [
            models.UniqueConstraint(fields=['staff', 'deduction'], name='unique_staff_salary_deduction'),
        ]
        verbose_name = 'スタッフ別差引額'
        verbose_name_plural = 'スタッフ別差引額'

    def __str__(self):
        return f'{self.staff} {self.deduction}: {self.amount}'


class MonthlyStaffSalaryDeduction(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='monthly_salary_deductions')
    deduction = models.ForeignKey(SalaryDeduction, on_delete=models.CASCADE, related_name='monthly_staff_amounts')
    month = models.DateField('対象月')
    amount = models.PositiveIntegerField('金額', default=0)
    is_active = models.BooleanField('適用', default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['staff', 'deduction', 'month'], name='unique_staff_deduction_month')]


class ShiftType(models.Model):
    code = models.CharField('区分', max_length=8, choices=SHIFT_TYPE_CODES, unique=True)
    color = models.CharField('色', max_length=7, choices=SHIFT_TYPE_COLORS + LEAVE_TYPE_COLORS, unique=True, blank=True, null=True)
    start_time = models.TimeField('開始時刻', blank=True, null=True)
    end_time = models.TimeField('終了時刻', blank=True, null=True)
    break_minutes = models.PositiveSmallIntegerField('休憩', choices=BREAK_MINUTE_CHOICES, blank=True, null=True)

    class Meta:
        ordering = ['code']
        verbose_name = '勤務区分'
        verbose_name_plural = '勤務区分'

    @property
    def is_leave(self):
        return self.code in dict(LEAVE_TYPE_CODES)

    @property
    def text_color(self):
        return (self.color or '#555555') if self.is_leave else '#2a171b'

    @property
    def background_color(self):
        return '#e8e8e8' if self.is_leave else (self.color or '')

    def __str__(self):
        if self.start_time and self.end_time:
            return f'{self.code} {self.start_time:%H:%M}-{self.end_time:%H:%M}'
        return self.code

    @property
    def overtime_start_label(self):
        if self.is_leave or not self.end_time:
            return '-'
        end = datetime.combine(datetime.today(), self.end_time)
        threshold = end + timedelta(minutes=15)
        prefix = '翌日 ' if threshold.date() != end.date() else ''
        return f'{prefix}{threshold:%H:%M}'

    @property
    def work_minutes(self):
        if not self.start_time or not self.end_time:
            return None
        start_at = datetime.combine(datetime.today(), self.start_time)
        end_at = datetime.combine(datetime.today(), self.end_time)
        minutes = int((end_at - start_at).total_seconds() // 60)
        return max(0, minutes - (self.break_minutes or 0))

    @property
    def work_duration_label(self):
        if self.work_minutes is None:
            return '時間なし'
        hours, minutes = divmod(self.work_minutes, 60)
        if minutes:
            return f'{hours}時間{minutes}分'
        return f'{hours}時間'


class Shift(models.Model):
    staff = models.ForeignKey(Staff, verbose_name='スタッフ', on_delete=models.CASCADE, related_name='shifts')
    shift_type = models.ForeignKey(
        ShiftType,
        verbose_name='勤務区分',
        on_delete=models.SET_NULL,
        related_name='shifts',
        blank=True,
        null=True,
    )
    work_date = models.DateField('勤務日')
    start_time = models.TimeField('開始時刻', blank=True, null=True)
    end_time = models.TimeField('終了時刻', blank=True, null=True)
    actual_start_time = models.TimeField('実働開始時刻', blank=True, null=True)
    actual_end_time = models.TimeField('実働終了時刻', blank=True, null=True)
    actual_day_off = models.BooleanField('実働休み', default=False)
    actual_shift_type = models.ForeignKey(
        ShiftType, verbose_name='実働区分', on_delete=models.SET_NULL,
        related_name='actual_shifts', blank=True, null=True,
    )
    actual_break_minutes = models.PositiveSmallIntegerField('実働休憩（分）', blank=True, null=True)

    @property
    def planned_break_minutes(self):
        return (self.shift_type.break_minutes or 0) if self.shift_type else 0

    @property
    def effective_break_minutes(self):
        category = self.effective_shift_type
        return self.actual_break_minutes if self.actual_break_minutes is not None else ((category.break_minutes or 0) if category else 0)

    @property
    def effective_shift_type(self):
        return self.actual_shift_type or self.shift_type

    @property
    def overtime_minutes(self):
        category = self.effective_shift_type
        if (self.actual_day_off or not category or category.is_leave
                or not category.end_time or not self.actual_start_time or not self.actual_end_time):
            return 0
        threshold = datetime.combine(self.work_date, category.end_time) + timedelta(minutes=15)
        start = max(threshold, datetime.combine(self.work_date, self.actual_start_time))
        end = datetime.combine(self.work_date, self.actual_end_time)
        return max(0, int((end - start).total_seconds() // 60))

    @property
    def actual_display_label(self):
        if self.actual_day_off:
            if self.actual_shift_type and self.actual_shift_type.is_leave:
                return self.actual_shift_type.code
            return '休'
        if self.actual_start_time and self.actual_end_time:
            return f'{self.actual_start_time:%H:%M}-{self.actual_end_time:%H:%M}'
        return '未登録'

    @property
    def actual_differs_from_plan(self):
        planned_off = bool(self.shift_type and self.shift_type.is_leave)
        if self.actual_day_off:
            return not planned_off or bool(self.actual_shift_type_id and self.actual_shift_type_id != self.shift_type_id)
        if self.actual_start_time and self.actual_end_time:
            return (planned_off or (self.actual_start_time, self.actual_end_time) != (self.start_time, self.end_time)
                    or self.effective_break_minutes != self.planned_break_minutes
                    or bool(self.actual_shift_type_id and self.actual_shift_type_id != self.shift_type_id))
        return False

    @property
    def actual_change_class(self):
        if not self.actual_differs_from_plan:
            return ''
        if self.actual_day_off:
            return 'actual-changed-off'
        if self.shift_type and self.shift_type.is_leave:
            return 'actual-changed-work'
        return 'actual-changed'

    role = models.CharField('担当', max_length=80, blank=True)
    memo = models.CharField('メモ', max_length=160, blank=True)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        ordering = ['work_date', 'start_time', 'staff__name']
        constraints = [
            models.UniqueConstraint(fields=['staff', 'work_date'], name='unique_staff_shift_per_day'),
        ]
        verbose_name = 'シフト'
        verbose_name_plural = 'シフト'

    def __str__(self):
        if self.start_time and self.end_time:
            return f'{self.staff} {self.work_date} {self.start_time}-{self.end_time}'
        return f'{self.staff} {self.work_date}'
