# fastapi_core/rag_service.py
import os
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
from pathlib import Path

# ---------- تنظیمات ----------
DB_NAME = os.environ.get('DB_NAME', 'school_db')
DB_USER = os.environ.get('DB_USER', 'school_user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')

# ---------- بارگذاری مدل‌ها ----------
OLLAMA_MODEL = 'mshojaei77/gemma3persian',  # یا "partai/dorna-llama3"
OLLAMA_URL = "http://ollama:11434"  # آدرس سرویس Ollama در Docker

# ---------- اتصال به PostgreSQL ----------
def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    # ایجاد افزونه در صورت عدم وجود
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.close()
    conn.autocommit = False
    # ثبت نوع vector در اتصال
    register_vector(conn)
    return conn

# ---------- توابع RAG ----------
def create_documents_table():
    """ایجاد جدول اسناد با پشتیبانی از بردار"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            title TEXT,
            content TEXT,
            embedding vector(384),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING ivfflat (embedding vector_cosine_ops)")
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Table 'documents' created successfully!")

def add_document(title, content, metadata=None):
    """افزودن یک سند جدید به پایگاه داده"""
    embedding = embedding_model.encode(content).tolist()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO documents (title, content, embedding, metadata) VALUES (%s, %s, %s, %s)",
        (title, content, embedding, json.dumps(metadata or {}))
    )
    conn.commit()
    cur.close()
    conn.close()

def add_documents_batch(documents_list):
    """افزودن چندین سند به‌صورت یکجا (بهینه‌تر)"""
    if not documents_list:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    for title, content, metadata in documents_list:
        embedding = embedding_model.encode(content).tolist()
        cur.execute(
            "INSERT INTO documents (title, content, embedding, metadata) VALUES (%s, %s, %s, %s)",
            (title, content, embedding, json.dumps(metadata or {}))
        )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {len(documents_list)} documents added in batch.")

def get_all_documents():
    """دریافت لیست تمام اسناد از پایگاه داده"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, metadata, created_at
        FROM documents
        ORDER BY created_at DESC
    """)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "id": r[0],
            "title": r[1],
            "chunks": r[2].get('chunk', 1) if r[2] else 1,
            "created_at": r[3].strftime('%Y-%m-%d %H:%M') if r[3] else None
        }
        for r in results
    ]

def search_documents(query, top_k=3):
    """جست‌وجوی اسناد مرتبط با سؤال"""
    query_embedding = embedding_model.encode(query).tolist()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, content, metadata, 1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        ORDER BY similarity DESC
        LIMIT %s
    """, (query_embedding, top_k))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def extract_answer(question, context):
    """استخراج پاسخ از متن با استفاده از مدل QA"""
    inputs = qa_tokenizer(question, context, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = qa_model(**inputs)
    
    answer_start = torch.argmax(outputs.start_logits)
    answer_end = torch.argmax(outputs.end_logits) + 1
    answer = qa_tokenizer.decode(inputs["input_ids"][0][answer_start:answer_end])
    
    # اگر پاسخ خالی یا بی‌ربط بود، متن پیش‌فرض برگردان
    if not answer.strip() or answer.strip() == "[CLS]":
        return None
    return answer.strip()

def generate_answer(query, context_docs):
    """تولید پاسخ با استفاده از Ollama"""
    if not context_docs:
        return "هیچ سند مرتبطی یافت نشد."

    # ساخت متن پرامپت از اسناد مرتبط
    context_text = "\n\n".join([f"عنوان: {doc[0]}\nمحتوا: {doc[1]}" for doc in context_docs[:3]])
    
    # پرامپت نهایی برای مدل
    prompt = f"""شما یک دستیار هوشمند برای یک مدرسه هستید. بر اساس اطلاعات موجود در اسناد زیر، به سوال کاربر پاسخ دهید.

### اسناد:
{context_text}

### سوال کاربر:
{query}

### پاسخ:"""

    try:
        # ارسال درخواست به Ollama
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            stream=False,
            options={
                'temperature': 0.3,  # برای پاسخ‌های دقیق‌تر
                'num_predict': 256,   # حداکثر تعداد توکن برای پاسخ
            }
        )
        answer = response['message']['content'].strip()
        
        # اگر پاسخ خالی یا بی‌ربط بود، یک پاسخ پیش‌فرض بده
        if not answer:
            return "پاسخی برای این سوال پیدا نشد."
        return answer

    except Exception as e:
        print(f"خطا در ارتباط با Ollama: {e}")
        # در صورت خطا، متن اولین سند را برگردان
        return f"متاسفم، در پردازش سوال شما خطایی رخ داد. مرتبط‌ترین سند:\n{context_docs[0][1][:300]}..."
    
def chat(query):
    """پایپ‌لاین کامل RAG: جست‌وجو + تولید پاسخ"""
    # 1. جست‌وجوی اسناد مرتبط
    docs = search_documents(query)
    
    # 2. اگر سندی پیدا نشد
    if not docs:
        return {
            "answer": "سلام! من یک دستیار هوشمند هستم که به سؤالات شما درباره‌ی اسناد مدرسه پاسخ می‌دهم. لطفاً سؤال خود را دقیق‌تر بپرسید یا از کتابخانه اسناد جدید آپلود کنید.",

        }
    
    # 3. تولید پاسخ با LLM (یا روش جایگزین)
    answer = generate_answer(query, docs)
    
    # 4. استخراج منابع
    sources = [{"title": doc[0], "similarity": round(doc[3], 3)} for doc in docs]
    
    return {
        "answer": answer,
        "sources": sources
    }