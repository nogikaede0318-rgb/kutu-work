from django import forms

from .models import MonthlyPaidLeave


class WagePeriodForm(forms.Form):
    effective_month = forms.DateField(label='適用開始月', input_formats=['%Y-%m'],
        widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month'}))
    hourly_wage = forms.IntegerField(label='平日（円）', min_value=0)
    holiday_hourly_wage = forms.IntegerField(label='土日祝日（円）', min_value=0, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.initial.get('saved'):
            self.fields['effective_month'].disabled = True


class BaseWagePeriodFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        months = [form.cleaned_data['effective_month'] for form in self.forms if form.cleaned_data]
        if len(months) != len(set(months)):
            raise forms.ValidationError('同じ適用開始月を複数登録することはできません。')


WagePeriodFormSet = forms.formset_factory(WagePeriodForm, formset=BaseWagePeriodFormSet,
                                        extra=0, min_num=1, validate_min=True, max_num=100, validate_max=True)


class MonthlyPaidLeaveForm(forms.ModelForm):
    class Meta:
        model = MonthlyPaidLeave
        fields = ['days', 'hours_per_day']
        widgets = {
            'days': forms.NumberInput(attrs={'min': 0, 'max': 31, 'step': '0.01'}),
            'hours_per_day': forms.NumberInput(attrs={'min': 0, 'max': 24, 'step': '0.01'}),
        }

    def clean(self):
        data = super().clean()
        if data.get('days', 0) > 0 and data.get('hours_per_day') == 0:
            self.add_error('hours_per_day', '有給日数を設定する場合は、1日あたりの時間を入力してください。')
        return data
