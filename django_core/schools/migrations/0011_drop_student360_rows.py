"""Student 360 and counseling are base (owner decision, Slice A.1): the student360 key no longer exists. Removes any rows an
earlier backfill may have created. Not reversible (nothing to restore: the key is gone)."""
from django.db import migrations


def forwards(apps, schema_editor):
    apps.get_model('schools', 'SchoolModule').objects.filter(module_key='student360').delete()


class Migration(migrations.Migration):
    dependencies = [('schools', '0010_backfill_school_modules')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
