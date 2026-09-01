# fastapi_core/main.py

import uuid
import os
import tempfile
import logging
from pathlib import Path

import joblib
import torch
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from rag_service import (
    chat,
    create_documents_table,
    add_document,
    add_documents_batch,
    get_all_documents,
    search_documents,
    delete_document_by_parent_id,
    delete_document,
)
from train_nn_model import StudentRiskModel

# ---------- تنظیمات لاگ با سطح DEBUG برای عیب‌یابی ----------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------- بارگذاری مدل PyTorch ----------
MODEL_DIR = Path(__file__).parent / "models"
model_path = MODEL_DIR / "student_risk_model.pth"
scaler_path = MODEL_DIR / "scaler.joblib"

if not model_path.exists() or not scaler_path.exists():
    raise RuntimeError("مدل یا scaler وجود ندارد. لطفاً train_nn_model.py را اجرا کنید.")

scaler = joblib.load(scaler_path)
input_dim = len(scaler.mean_)
risk_model = StudentRiskModel(input_dim=input_dim)
risk_model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
risk_model.eval()
logger.info("✅ مدل پیش‌بینی ریسک با موفقیت بارگذاری شد.")

# ---------- راه‌اندازی FastAPI و جدول اسناد ----------
app = FastAPI(title="School AI Platform", description="سرویس یکپارچه هوش مصنوعی مدرسه", version="2.0.0")

try:
    create_documents_table()
    logger.info("✅ جدول اسناد با موفقیت ایجاد شد.")
except Exception as e:
    logger.error(f"❌ خطا در ایجاد جدول اسناد: {e}", exc_info=True)

# ---------- مدل‌های Pydantic ----------
class ChatRequest(BaseModel):
    query: str

class DocumentRequest(BaseModel):
    title: str
    content: str
    metadata: Optional[dict] = {}

class StudentFeatures(BaseModel):
    grade: int
    attendance_rate: float
    avg_completion_rate: float
    avg_exam_score: float
    total_absences: int
    total_lates: int
    total_communications: int
    completed_homework: int

class UploadResponse(BaseModel):
    status: str
    message: str
    chunks: int

# ---------- تابع کمکی ----------
def extract_text_from_pdf(pdf_path: str) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        page_text = page.get_text("text")
        if page_text:
            text += page_text + "\n\n"
    doc.close()
    return text

# ==================== اندپوینت‌ها ====================

@app.get("/")
async def read_root():
    return {"message": "School AI Platform is running!", "status": "healthy"}

@app.post("/predict/")
async def predict_risk(features: StudentFeatures):
    try:
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
        input_scaled = scaler.transform(input_data)
        with torch.no_grad():
            tensor_input = torch.tensor(input_scaled, dtype=torch.float32)
            output = risk_model(tensor_input)
            risk_prob = output.item()
            is_risk = risk_prob > 0.5
        return {
            "risk_probability": round(risk_prob, 4),
            "is_high_risk": is_risk,
            "message": "دانش‌آموز در معرض ریسک افت تحصیلی است." if is_risk else "دانش‌آموز وضعیت مطلوبی دارد."
        }
    except Exception as e:
        logger.error(f"خطا در پیش‌بینی: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در پردازش پیش‌بینی: {str(e)}")

@app.post("/chat/")
async def chat_endpoint(request: ChatRequest):
    try:
        result = chat(request.query)
        return result
    except Exception as e:
        logger.error(f"خطا در چت: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در پردازش سؤال: {str(e)}")

@app.post("/documents/")
async def add_document_endpoint(request: DocumentRequest):
    try:
        add_document(request.title, request.content, request.metadata)
        return {"status": "success", "message": "سند با موفقیت اضافه شد."}
    except Exception as e:
        logger.error(f"خطا در افزودن سند: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در افزودن سند: {str(e)}")

@app.get("/documents/list/")
async def list_documents():
    try:
        docs = get_all_documents()
        return {"documents": docs}
    except Exception as e:
        logger.error(f"خطا در دریافت لیست اسناد: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در دریافت لیست اسناد: {str(e)}")

@app.get("/documents/search/")
async def search_documents_endpoint(query: str, top_k: int = 3):
    try:
        results = search_documents(query, top_k)
        return {
            "results": [
                {"title": r[0], "content": r[1][:200] + "...", "similarity": r[3]}
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"خطا در جستجوی اسناد: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در جستجوی اسناد: {str(e)}")

@app.post("/upload-document/", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    try:
        logger.info(f"دریافت فایل: {file.filename}")

        suffix = os.path.splitext(file.filename)[1].lower()
        if suffix not in ['.pdf', '.docx', '.doc']:
            raise HTTPException(status_code=400, detail="فرمت فایل پشتیبانی نمی‌شود.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        text = ""
        try:
            if suffix == '.pdf':
                import fitz
                doc = fitz.open(tmp_path)
                for page in doc:
                    page_text = page.get_text("text")
                    if page_text:
                        text += page_text + "\n\n"
                doc.close()
            elif suffix in ['.docx', '.doc']:
                import docx
                doc = docx.Document(tmp_path)
                text = "\n".join([para.text for para in doc.paragraphs])
        finally:
            os.unlink(tmp_path)

        if not text.strip():
            raise HTTPException(status_code=400, detail="متن استخراج‌شده خالی است.")

        from langchain.text_splitter import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=100,
            separators=["\n\n", "\n", "،", ".", " ", ""]
        )
        chunks = splitter.split_text(text)

        parent_id = str(uuid.uuid4())
        title = os.path.splitext(file.filename)[0]
        total_chunks = len(chunks)

        documents_to_add = []
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                chunk_title = f"{title} - بخش {i+1}"
                metadata = {
                    "source": file.filename,
                    "chunk": i + 1,
                    "total_chunks": total_chunks
                }
                documents_to_add.append((chunk_title, chunk, metadata, parent_id))

        logger.debug(f"تعداد اسناد برای افزودن: {len(documents_to_add)}")
        if documents_to_add:
            # بررسی ساختار اولین سند برای اطمینان
            logger.debug(f"نمونه سند اول: {documents_to_add[0]}")
            add_documents_batch(documents_to_add)

        logger.info(f"فایل {file.filename} با موفقیت پردازش شد. تعداد قطعات: {len(chunks)}")

        return UploadResponse(
            status="success",
            message=f"فایل با موفقیت بارگذاری شد و به {len(chunks)} بخش تقسیم شد.",
            chunks=len(chunks)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در پردازش فایل: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در پردازش فایل: {str(e)}")

@app.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: int):
    try:
        deleted = delete_document(doc_id)
        if deleted:
            return {"status": "success", "message": "سند با موفقیت حذف شد."}
        else:
            raise HTTPException(status_code=404, detail="سند پیدا نشد.")
    except Exception as e:
        logger.error(f"خطا در حذف سند: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در حذف سند: {str(e)}")

@app.delete("/documents/parent/{parent_id}")
async def delete_document_by_parent_endpoint(parent_id: str):
    try:
        deleted = delete_document_by_parent_id(parent_id)
        if deleted:
            return {"status": "success", "message": "فایل با موفقیت حذف شد."}
        else:
            raise HTTPException(status_code=404, detail="فایل پیدا نشد.")
    except Exception as e:
        logger.error(f"خطا در حذف فایل: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"خطا در حذف فایل: {str(e)}")