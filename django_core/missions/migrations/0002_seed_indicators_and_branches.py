from django.db import migrations

from missions.defaults import BRANCHES, INDICATORS


def seed(apps, schema_editor):
    Indicator, Branch = apps.get_model('missions', 'Indicator'), apps.get_model('missions', 'Branch')
    for code, name in INDICATORS:
        Indicator.objects.update_or_create(code=code, defaults={'name_fa': name})
    for order, (code, field, name) in enumerate(BRANCHES, start=1):
        Branch.objects.update_or_create(code=code, defaults={'field': field, 'name_fa': name, 'order': order})


class Migration(migrations.Migration):
    dependencies = [('missions', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
