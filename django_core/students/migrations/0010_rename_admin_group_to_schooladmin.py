"""Rename auth Group 'Admin' -> 'SchoolAdmin' (ADR-0010 decision 2, owner-approved 2026-10-16).

An in-place update of the same row: group id, members and permissions are preserved. Reversible.
If the target name already exists the migration raises and changes nothing (no silent merge).
The names are literals on purpose: a migration is a frozen record, not code that follows the constants.
"""
from django.db import migrations

OLD, NEW = 'Admin', 'SchoolAdmin'


def _rename(apps, old, new):
    Group = apps.get_model('auth', 'Group')
    source = Group.objects.filter(name=old)
    if not source.exists():
        return  # fresh database: setup/seed creates the group under the current name
    if Group.objects.filter(name=new).exists():
        raise RuntimeError(
            f"Cannot rename group '{old}' to '{new}': a group named '{new}' already exists. "
            "Resolve it manually (nothing was changed).")
    source.update(name=new)


def forwards(apps, schema_editor):
    _rename(apps, OLD, NEW)


def backwards(apps, schema_editor):
    _rename(apps, NEW, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0009_link_students_to_classes'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
