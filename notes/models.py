from datetime import datetime

from django.db import models


SHIFT_TYPE_CODES = [('休', '休')] + [(chr(code), chr(code)) for code in range(ord('A'), ord('Z') + 1)]
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
    management_number = models.CharField('管理番号', max_length=2, unique=True, blank=True, null=True)
    name = models.CharField('名前', max_length=80, unique=True)
    hourly_wage = models.PositiveIntegerField('時給', default=0)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)

    class Meta:
        ordering = [models.F('management_number').asc(nulls_last=True), 'name']
        verbose_name = 'スタッフ'
        verbose_name_plural = 'スタッフ'

    def __str__(self):
        return self.name


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


class ShiftType(models.Model):
    code = models.CharField('区分', max_length=1, choices=SHIFT_TYPE_CODES, unique=True)
    color = models.CharField('色', max_length=7, choices=SHIFT_TYPE_COLORS, unique=True, blank=True, null=True)
    start_time = models.TimeField('開始時刻', blank=True, null=True)
    end_time = models.TimeField('終了時刻', blank=True, null=True)
    break_minutes = models.PositiveSmallIntegerField('休憩', choices=BREAK_MINUTE_CHOICES, blank=True, null=True)

    class Meta:
        ordering = ['code']
        verbose_name = '勤務区分'
        verbose_name_plural = '勤務区分'

    def __str__(self):
        if self.start_time and self.end_time:
            return f'{self.code} {self.start_time:%H:%M}-{self.end_time:%H:%M}'
        return self.code

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
