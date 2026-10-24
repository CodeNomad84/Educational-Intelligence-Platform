"""Existing schools keep what they have today: tutor_ai, plus advisor_ai where the
demo app is installed. Nothing is switched off on deploy. Reverse removes only these backfilled rows."""
from django.apps import apps as global_apps
from django.db import migrations
from django.utils import timezone

KEYS = ('tutor_ai',)


def forwards(apps, schema_editor):
    School = apps.get_model('schools', 'School')
    SchoolModule = apps.get_model('schools', 'SchoolModule')
    keys = KEYS + (('advisor_ai',) if global_apps.is_installed('demo_intel') else ())
    today = timezone.localdate()
    for school_id in School.objects.values_list('pk', flat=True):
        for key in keys:
            SchoolModule.objects.get_or_create(school_id=school_id, module_key=key, starts_on=today)


def backwards(apps, schema_editor):
    apps.get_model('schools', 'SchoolModule').objects.filter(
        module_key__in=KEYS + ('advisor_ai',), ends_on__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('schools', '0009_schoolmodule')]
    operations = [migrations.RunPython(forwards, backwards)]
