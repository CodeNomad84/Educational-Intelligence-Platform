"""Django-owned creation of the RAG ``documents`` table (Phase 1, ADR-0001 PROPOSED).

Previously FastAPI created (and, on a dimension mismatch, DROPPED) this table at startup.
Django now owns the schema. Properties:
  * PostgreSQL only (needs pgvector); a no-op on other databases (e.g. the sqlite dev DB).
  * Idempotent and non-destructive: ``IF NOT EXISTS`` everywhere, never drops anything.
    An existing table created by the old FastAPI code is left untouched.
  * Vector dimension is fixed at 1024 (the previous fallback/default for qwen3-embedding:0.6b).
    DECISION REQUIRED: dimension policy when the embedding model changes (ADR-0001).
NOT VERIFIED on a real PostgreSQL+pgvector server in Phase 1 (none available in the sandbox).
"""
from django.db import migrations

EMBEDDING_DIM = 1024

CREATE_SQL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        parent_id TEXT,
        title TEXT,
        content TEXT,
        embedding vector({EMBEDDING_DIM}),
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents USING ivfflat (embedding vector_cosine_ops)
    """,
]


def create_documents_table(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for statement in CREATE_SQL:
        schema_editor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0006_document'),
    ]

    operations = [
        # No reverse: dropping a table that may hold user documents is never automatic.
        migrations.RunPython(create_documents_table, migrations.RunPython.noop),
    ]
