from django.db import migrations


def create_leave_types(apps, schema_editor):
    ShiftType = apps.get_model('notes', 'ShiftType')
    for code, color in [('希望休', '#DC2626'), ('指定休', '#222222'), ('その他', '#F97316')]:
        ShiftType.objects.using(schema_editor.connection.alias).get_or_create(code=code, defaults={'color': color})


class Migration(migrations.Migration):
    dependencies = [('notes', '0024_alter_shifttype_code_alter_shifttype_color')]
    operations = [migrations.RunPython(create_leave_types, migrations.RunPython.noop)]
