"""Documents get a school (S5): ``documents.school_id`` (Django owns the schema, FastAPI only reads/writes rows).

PostgreSQL only (the table exists only there, see 0007). Idempotent and non-destructive; existing rows get NULL, and a
plain integer, no foreign key: the table is not a Django model, so a FK would break TRUNCATE in
flushes; schools are never deleted, ``School`` is PROTECTed everywhere). A document with ``school_id IS NULL`` is visible to nobody (FastAPI filters ``school_id = ANY(token.schools)``). No reverse:
dropping a column that holds ownership information is never automatic.
"""
from django.db import migrations

SQL = [
    "ALTER TABLE IF EXISTS documents ADD COLUMN IF NOT EXISTS school_id INTEGER",
    "CREATE INDEX IF NOT EXISTS documents_school_idx ON documents (school_id)",
]


def add_school_column(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for statement in SQL:
        schema_editor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0019_phones_and_recommendation_visibility'),
        ('schools', '0006_auditevent'),
    ]

    operations = [
        migrations.RunPython(add_school_column, migrations.RunPython.noop),
    ]
