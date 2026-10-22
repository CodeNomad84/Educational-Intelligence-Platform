"""S6 (changes/0010): ``Student.school`` becomes NOT NULL.

Step 1 is a guard: if any student still has no school the migration STOPS with a message that names the rows' count
and the tools that fix it; nothing is changed (the whole migration runs in one transaction on SQLite and PostgreSQL).
Step 2 is the column change. The migration never assigns a school itself: only ``backfill_student_school`` may populate
a legacy row (owner requirement 1); run ``check_student_school_ready`` first.

Reverse: the column becomes nullable again (the guard has nothing to undo). The information that a row was once
unassigned is not restored: the schema is reversible, the data meaning is not.
"""
import django.db.models.deletion
from django.db import migrations, models


class StudentsWithoutSchool(Exception):
    """Raised by the guard of students.0015; the database is left unchanged."""


def refuse_while_students_have_no_school(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    missing = Student.objects.using(schema_editor.connection.alias).filter(school__isnull=True).count()
    if missing:
        raise StudentsWithoutSchool(
            f'students.0015 refused: {missing} student(s) have no school. Nothing was changed. Run '
            '"manage.py check_student_school_ready", then "manage.py backfill_student_school" (dry run first), '
            'and migrate again once check_student_school_ready says READY.')


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0014_rollover_choices'),
        ('schools', '0004_schoolmembership'),
    ]

    operations = [
        migrations.RunPython(refuse_while_students_have_no_school, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='student',
            name='school',
            field=models.ForeignKey(
                editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='students',
                to='schools.school', verbose_name='مدرسه'),
        ),
    ]
