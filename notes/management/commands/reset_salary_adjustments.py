import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from notes.models import MonthlyStaffSalaryDeduction, SalaryDeduction, Staff, StaffSalaryDeduction


def backup_database():
    if connection.vendor != 'sqlite':
        raise CommandError('このコマンドはSQLite専用です。')
    source = Path(connection.settings_dict['NAME']).resolve()
    if not source.is_file():
        raise CommandError('SQLiteファイルが見つかりません。')
    folder = source.parent / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / f'{source.stem}_before_adjustment_reset_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3'
    with sqlite3.connect(source) as original, sqlite3.connect(target) as backup:
        original.backup(backup)
    return target


class Command(BaseCommand):
    help = '指定月以降の全スタッフの加減項目をOFF・0円にします（過去は保持）。'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--from-month', required=True, help='開始月（例: 2026-10）')
        parser.add_argument('--apply', action='store_true', help='バックアップを作成して変更を実行')

    def handle(self, *args, **options):
        value = options['from_month']
        try:
            if not re.fullmatch(r'\d{4}-\d{2}', value):
                raise ValueError
            cutoff = date.fromisoformat(value + '-01')
        except ValueError:
            raise CommandError('開始月はYYYY-MM形式で指定してください。')
        self.stdout.write(f'対象DB: {connection.settings_dict["NAME"]}')
        self.stdout.write(f'{value}以降: 全スタッフ {Staff.objects.count()}名 × 加減項目 {SalaryDeduction.objects.count()}件をOFF・0円にします。')
        if not options['apply']:
            self.stdout.write('確認のみです。実行するには --apply を付けてください。')
            return
        backup = backup_database()
        self.stdout.write(f'バックアップ: {backup}')
        with transaction.atomic():
            for staff in Staff.objects.all():
                for deduction in SalaryDeduction.objects.all():
                    setting, _ = StaffSalaryDeduction.objects.get_or_create(
                        staff=staff, deduction=deduction,
                        defaults={'amount': deduction.fixed_amount if deduction.amount_type == 'fixed' else 0,
                                  'is_active': deduction.amount_type == 'fixed'},
                    )
                    # Keep any previous reset boundary so earlier months remain unchanged.
                    if setting.reset_from_month is None or setting.reset_from_month > cutoff:
                        setting.reset_from_month = cutoff
                        setting.save(update_fields=['reset_from_month'])
            MonthlyStaffSalaryDeduction.objects.filter(month__gte=cutoff).update(amount=0, is_active=False)
        self.stdout.write(self.style.SUCCESS('リセット完了。開始月より前の設定は保持しました。'))
