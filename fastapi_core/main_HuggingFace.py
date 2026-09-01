# fastapi_core/main.py

'''
در این کد از FastAPI برای ایجاد یک سرویس وب استفاده شده است که شامل دو بخش اصلی است:
1. پیش‌بینی ریسک افت تحصیلی دانش‌آموزان با استفاده از یک مدل PyTorch و scaler از joblib.
2. سیستم RAG (Retrieval-Augmented Generation) برای پاسخ به سوالات کاربران بر اساس اسناد موجود، با استفاده از مدل‌های Oll
ama برای تولید پاسخ و embedding.
- مدل embedding: مدل‌های HuggingFace مشخص شده در کد fastapi_core/rag_service_HuggingFace_Models.py (بردار 768 بعدی)
- مدل LLM: مدل‌های HuggingFace مشخص شده در کد fastapi_core/rag_service_HuggingFace_Models.py (بردار 768 بعدی)
- اتصال به پایگاه داده PostgreSQL با پشتیبانی از pgvector برای ذخیره و جستجوی بردارها
- توابع مدیریت جدول، افزودن اسناد، جستجو و تولید پاسخ با LLM
- لاگ‌گیری برای خطاها و عملیات موفق
'''

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, UploadFile, File
from rag_service import chat, create_documents_table, add_document, add_documents_batch
from rag_service import get_all_documents
import os
import fitz
import tempfile
import joblib
import torch
import numpy as np
from pathlib import Path
from train_nn_model import StudentRiskModel


# بارگذاری مدل هنگام راه‌اندازی سرویس
# model_path = os.path.join(os.path.dirname(__file__), "student_model.joblib")
# if os.path.exists(model_path):
#     model = joblib.load(model_path)
# else:
#     model = None
#     print("WARNING: مدل پیدا نشد! لطفاً train_model.py را اجرا کنید.")

# ---------- بارگذاری مدل و scaler ----------
MODEL_DIR = Path(__file__).parent / "models"
model_path = MODEL_DIR / "student_risk_model.pth"
scaler_path = MODEL_DIR / "scaler.joblib"

if not model_path.exists() or not scaler_path.exists():
    raise RuntimeError("مدل یا scaler وجود ندارد. لطفاً train_nn_model.py را اجرا کنید.")

# بارگذاری scaler
scaler = joblib.load(scaler_path)

# بارگذاری مدل
input_dim = len(scaler.mean_)  # تعداد ویژگی‌ها
model = StudentRiskModel(input_dim=input_dim)
model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
model.eval()

app = FastAPI()

# ایجاد جدول اسناد در صورت عدم وجود
create_documents_table()

# ---------- مدل داده‌ی ورودی ----------
class ChatRequest(BaseModel):
    query: str

class DocumentRequest(BaseModel):
    title: str
    content: str
    metadata: dict = {}
# ---------- مدل داده‌ی ورودی ----------
# class StudentFeatures(BaseModel):
#     avg_score: float   # میانگین نمرات (۰ تا ۲۰)
#     absences: int      # تعداد غیبت‌ها
# ---------- مدل داده‌ی ورودی (ویژگی‌های مورد نیاز) ----------
class StudentFeatures(BaseModel):
    grade: int
    attendance_rate: float
    avg_completion_rate: float
    avg_exam_score: float
    total_absences: int
    total_lates: int
    total_communications: int
    completed_homework: int

def extract_text_from_pdf(pdf_path):
    """استخراج متن از PDF با حفظ ترتیب کاراکترهای فارسی"""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        # استخراج متن با حفظ ترتیب
        page_text = page.get_text("text")
        if page_text:
            text += page_text + "\n\n"
    doc.close()
    return text
# ---------- اندپوینت‌ها ----------
# @app.get("/")
# def read_root():
#     return {"message": "FastAPI Core is running!"}
@app.get("/")
def read_root():
    return {"message": "FastAPI Core with PyTorch is running!"}


# ---------- اندپوینت جدید پیش‌بینی ----------
# @app.post("/predict/")
# def predict_student_status(features: StudentFeatures):
#     """
#     دریافت میانگین نمرات و تعداد غیبت‌ها و پیش‌بینی وضعیت دانش‌آموز
#     """
#     if model is None:
#         raise HTTPException(status_code=503, detail="مدل هنوز بارگذاری نشده است.")
    
#     # تبدیل ورودی به آرایه‌ی numpy با شکل (۱, ۲)
#     input_data = np.array([[features.avg_score, features.absences]])
    
#     # پیش‌بینی
#     prediction = model.predict(input_data)[0]
#     probability = model.predict_proba(input_data)[0]
    
#     # تفسیر خروجی
#     status = "موفق" if prediction == 1 else "نیاز به تلاش بیشتر"
    
#     return {
#         "prediction": int(prediction),
#         "status": status,
#         "confidence": float(max(probability)),
#         "input_data": features.dict()
#     }
@app.post("/predict/")
def predict_risk(features: StudentFeatures):
    # 1. تبدیل به آرایه
    input_data = np.array([[
        features.grade,
        features.attendance_rate,
        features.avg_completion_rate,
        features.avg_exam_score,
        features.total_absences,
        features.total_lates,
        features.total_communications,
        features.completed_homework
    ]])
    
        # 2. استانداردسازی
    input_scaled = scaler.transform(input_data)
    
    # 3. پیش‌بینی
    with torch.no_grad():
        tensor_input = torch.tensor(input_scaled, dtype=torch.float32)
        output = model(tensor_input)
        risk_prob = output.item()
        is_risk = risk_prob > 0.5
    
    return {
        "risk_probability": round(risk_prob, 4),
        "is_high_risk": is_risk,
        "message": "دانش‌آموز در معرض ریسک افت تحصیلی است." if is_risk else "دانش‌آموز وضعیت مطلوبی دارد."
    }

@app.post("/chat/")
def chat_endpoint(request: ChatRequest):
    try:
        result = chat(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در پردازش سؤال: {str(e)}")

@app.post("/documents/")
def add_document_endpoint(request: DocumentRequest):
    try:
        add_document(request.title, request.content, request.metadata)
        return {"status": "success", "message": "سند با موفقیت اضافه شد."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در افزودن سند: {str(e)}")

@app.get("/documents/search/")
def search_documents_endpoint(query: str, top_k: int = 3):
    from rag_service import search_documents
    results = search_documents(query, top_k)
    return {
        "results": [
            {"title": r[0], "content": r[1][:200] + "...", "similarity": r[3]}
            for r in results
        ]
    }

import logging
logging.basicConfig(level=logging.INFO)

@app.post("/upload-document/")
async def upload_document(file: UploadFile = File(...)):
    try:
        logging.info(f"دریافت فایل: {file.filename}")
        
        # 1. بررسی پسوند
        suffix = os.path.splitext(file.filename)[1].lower()
        if suffix not in ['.pdf', '.docx', '.doc']:
            raise HTTPException(status_code=400, detail="فرمت فایل پشتیبانی نمی‌شود. فقط PDF و Word مجاز است.")
        
        # 2. ذخیره موقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # 3. استخراج متن
        text = ""
        try:
            if suffix == '.pdf':
                text = extract_text_from_pdf(tmp_path)
                # اگر می‌خواهید از pdfplumber استفاده کنید، می‌توانید کد زیر را جایگزین کنید:
                # import pdfplumber
                # with pdfplumber.open(tmp_path) as pdf:
                #     for page in pdf.pages:
                #         page_text = page.extract_text()
                #         if page_text:
                #             text += page_text + "\n"
            elif suffix in ['.docx', '.doc']:
                import docx
                doc = docx.Document(tmp_path)
                text = "\n".join([para.text for para in doc.paragraphs])
        finally:
            os.unlink(tmp_path)  # حذف فایل موقت
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="متن استخراج‌شده خالی است.")
        
        # 4. تقسیم به قطعات
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,  
            chunk_overlap=100,
            separators=["\n\n", "\n", "،", ".", " ", ""]
        )
        chunks = splitter.split_text(text)
        
        # 5. ذخیره در دیتابیس
        title = os.path.splitext(file.filename)[0]
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                chunk_title = f"{title} - بخش {i+1}"
                add_document(chunk_title, chunk, {"source": file.filename, "chunk": i+1})
        
        logging.info(f"فایل {file.filename} با موفقیت پردازش شد. تعداد قطعات: {len(chunks)}")
        
        return {
            "status": "success",
            "message": f"فایل با موفقیت بارگذاری شد و به {len(chunks)} بخش تقسیم شد.",
            "chunks": len(chunks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"خطا در پردازش فایل: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در پردازش فایل: {str(e)}")
    
@app.get("/documents/list/")
def list_documents():
    """دریافت لیست تمام اسناد"""
    try:
        docs = get_all_documents()
        return {"documents": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت لیست اسناد: {str(e)}")