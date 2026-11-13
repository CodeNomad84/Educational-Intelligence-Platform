# fastapi_core/rag_service.py
"""
سرویس RAG با استفاده از Ollama و PostgreSQL + pgvector
- مدل embedding: qwen3-embedding:0.6b (ابعاد به‌صورت پویا تشخیص داده می‌شود)
- مدل LLM: mshojaei77/gemma3persian (قابل تنظیم با متغیر محیطی)
- پشتیبانی از parent_id برای گروه‌بندی بخش‌های یک فایل
- لاگ‌گیری برای خطاها و عملیات موفق
"""

import os
import json
import psycopg2
from pgvector.psycopg2 import register_vector
import logging
from typing import List, Tuple, Dict, Any
from ollama import Client

# ---------- تنظیمات اولیه ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_NAME = os.environ.get('DB_NAME', 'school_db')
DB_USER = os.environ.get('DB_USER', 'school_user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')

OLLAMA_HOST = "http://ollama:11434"
OLLAMA_LLM_MODEL = os.environ.get('OLLAMA_LLM_MODEL', 'mshojaei77/gemma3persian')
OLLAMA_EMBED_MODEL = os.environ.get('OLLAMA_EMBED_MODEL', 'qwen3-embedding:0.6b')

# ایجاد کلاینت Ollama
client = Client(host=OLLAMA_HOST)

# ---------- تشخیص ابعاد بردار ----------
def get_embedding_dim() -> int:
    try:
        sample_text = "test"
        response = client.embeddings(
            model=OLLAMA_EMBED_MODEL,
            prompt=sample_text,
            options={'num_predict': 1}
        )
        return len(response['embedding'])
    except Exception as e:
        logger.error(f"خطا در تشخیص ابعاد embedding: {e}")
        return 1024  # مقدار پیش‌فرض

EMBEDDING_DIM = get_embedding_dim()
logger.info(f"✅ ابعاد بردار تشخیص داده شد: {EMBEDDING_DIM}")

# ---------- اتصال به PostgreSQL ----------
DB_USER_READONLY = os.environ.get('DB_USER_READONLY', 'fastapi_user')
DB_PASSWORD_READONLY = os.environ.get('DB_PASSWORD_READONLY', '')

def get_db_connection(readonly=False):
    if readonly:
        user = DB_USER_READONLY
        password = DB_PASSWORD_READONLY
    else:
        user = DB_USER
        password = DB_PASSWORD
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    # The pgvector extension is created by a Django migration (students/0007); no DDL here.
    register_vector(conn)
    return conn

# ---------- بررسی جدول (فقط‌خواندنی) ----------
def documents_table_exists() -> bool:
    """Read-only check. The ``documents`` table is created by Django migrations
    (students/0007_rag_documents_table); FastAPI never creates, alters or drops schema."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.documents') IS NOT NULL")
        exists = bool(cur.fetchone()[0])
        cur.close()
        return exists
    finally:
        conn.close()

# ---------- توابع تولید بردار ----------
class EmbeddingError(RuntimeError):
    """The embedding model is unavailable. Never replaced by a placeholder vector."""


def get_embedding(text: str) -> List[float]:
    try:
        response = client.embeddings(
            model=OLLAMA_EMBED_MODEL,
            prompt=text,
            options={'num_predict': 1}
        )
        return response['embedding']
    except Exception as e:
        # Log the cause server-side; raise a generic message so callers cannot store or search
        # with a fake (zero) vector and API responses do not leak internals.
        logger.error(f"خطا در تولید embedding: {e}")
        raise EmbeddingError("Embedding model is unavailable.") from None

# ---------- توابع مدیریت اسناد ----------
def add_document(title: str, content: str, school_id: int, parent_id: str = None, metadata: Dict[str, Any] = None):
    """``school_id`` is required: a document without a school is visible to nobody."""
    embedding = get_embedding(content)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents (title, content, embedding, metadata, parent_id, school_id) 
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (title, content, embedding, json.dumps(metadata or {}), parent_id, school_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"✅ Document '{title}' added successfully!")

def add_documents_batch(documents_list: List[Tuple[str, str, Dict, str]], school_id: int):
    if not documents_list:
        return
    # Embed everything BEFORE opening a DB connection: an embedding failure then raises without
    # leaving a connection/transaction behind and without writing any row.
    embeddings = [get_embedding(content) for _, content, _, _ in documents_list]
    conn = get_db_connection()
    cur = conn.cursor()
    for (title, content, metadata, parent_id), embedding in zip(documents_list, embeddings):
        cur.execute(
            """
            INSERT INTO documents (title, content, embedding, metadata, parent_id, school_id) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (title, content, embedding, json.dumps(metadata or {}), parent_id, school_id)
        )
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"✅ {len(documents_list)} documents added in batch.")

# ---------- توابع جستجو ----------
def search_documents(query: str, top_k: int = 3, school_ids: List[int] = ()) -> List[Tuple]:
    """ACL BEFORE ranking: only documents of the caller's schools are candidates (no schools = nothing)."""
    query_embedding = get_embedding(query)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, content, metadata, 1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        WHERE school_id = ANY(%s)
        ORDER BY similarity DESC
        LIMIT %s
    """, (query_embedding, list(school_ids), top_k))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def get_all_documents(school_ids: List[int] = ()) -> List[Dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        WITH file_info AS (
            SELECT 
                parent_id,
                MIN(id) as id,
                MIN(title) as title,
                MIN(metadata::text) as metadata_text,
                MIN(created_at) as created_at,
                COUNT(*) as total_chunks
            FROM documents
            WHERE school_id = ANY(%s)
            GROUP BY parent_id
            ORDER BY MIN(created_at) DESC
        )
        SELECT id, parent_id, title, metadata_text::jsonb, created_at, total_chunks
        FROM file_info
    """, (list(school_ids),))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "parent_id": r[1],
            "title": r[2].replace(" - بخش ۱", "").replace(" - بخش 1", ""),
            "chunks": r[5],
            "created_at": r[4].strftime('%Y-%m-%d %H:%M') if r[4] else None
        }
        for r in results
    ]

# ---------- توابع تولید پاسخ با LLM ----------
def generate_answer_with_llm(query: str, context_docs: List[Tuple]) -> str:
    if not context_docs:
        return "هیچ سند مرتبطی یافت نشد."

    context_text = "\n\n".join([
        f"عنوان: {doc[0]}\nمحتوا: {doc[1]}" 
        for doc in context_docs[:3]
    ])
    
    system_prompt = """شما یک دستیار هوشمند برای یک مدرسه هستید. 
بر اساس اطلاعات موجود در اسناد زیر، به سوال کاربر پاسخ دهید.
اگر پاسخ در اسناد وجود ندارد، به‌خوبی توضیح دهید که اطلاعاتی در این مورد ندارید و پیشنهاد دهید سوال را دقیق‌تر بپرسند.
پاسخ باید مختصر، مفید و به زبان فارسی باشد."""

    user_prompt = f"""### اسناد:
{context_text}

### سوال کاربر:
{query}

### پاسخ:"""

    try:
        response = client.chat(
            model=OLLAMA_LLM_MODEL,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            stream=False,
            options={
                'temperature': 0.3,
                'num_predict': 256,
                'top_p': 0.9,
                'repeat_penalty': 1.1,
            }
        )
        answer = response['message']['content'].strip()
        if not answer:
            return "پاسخی برای این سوال پیدا نشد."
        return answer

    except Exception as e:
        logger.error(f"خطا در تولید پاسخ با LLM: {e}")
        best_doc = context_docs[0]
        return f"متاسفم، در پردازش سوال شما خطایی رخ داد. مرتبط‌ترین سند:\n\n{best_doc[1][:500]}..."

def delete_document(doc_id: int, school_ids: List[int] = ()) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documents WHERE id = %s AND school_id = ANY(%s)", (doc_id, list(school_ids)))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        logger.info(f"✅ Document with id {doc_id} deleted successfully.")
    else:
        logger.warning(f"⚠️ Document with id {doc_id} not found.")
    return deleted

def delete_document_by_parent_id(parent_id: str, school_ids: List[int] = ()) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documents WHERE parent_id = %s AND school_id = ANY(%s)", (parent_id, list(school_ids)))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        logger.info(f"✅ Documents with parent_id {parent_id} deleted successfully.")
    else:
        logger.warning(f"⚠️ No documents found with parent_id {parent_id}.")
    return deleted

# ---------- تابع اصلی چت ----------
def chat(query: str, school_ids: List[int] = ()) -> Dict:
    docs = search_documents(query, school_ids=school_ids)
    if not docs:
        return {
            "answer": "متأسفم، هیچ سند مرتبطی با سؤال شما پیدا نشد. لطفاً سؤال خود را دقیق‌تر بپرسید یا از طریق کتابخانه اسناد جدید آپلود کنید.",
            "sources": []
        }
    answer = generate_answer_with_llm(query, docs)
    sources = [
        {"title": doc[0], "similarity": round(doc[3], 3)} 
        for doc in docs
    ]
    return {
        "answer": answer,
        "sources": sources
    }