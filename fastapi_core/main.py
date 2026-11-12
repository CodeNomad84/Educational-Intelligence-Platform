# fastapi_core/main.py

import uuid
import os
import tempfile
import logging
from pathlib import Path

from auth import (
    require_roles, require_roles_with_schools, school_ids, disabled_in_phase1, validate_service_secret, ADMIN, TEACHER)
import joblib
import torch
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional
from fastapi import APIRouter


router_v1 = APIRouter(prefix="/api/v1")


from rag_service import (
    chat,
    documents_table_exists,
    add_document,
    add_documents_batch,
    get_all_documents,
    search_documents,
    delete_document_by_parent_id,
    delete_document,
)
from train_nn_model import StudentRiskModel
import llm_adapter

# ---------- تنظیمات لاگ با سطح DEBUG برای عیب‌یابی ----------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def _internal_error(exc, where, detail='internal_error'):
    """M-3 (T7): a 500 tells the client nothing about the failure and carries a correlation id.

    The exception text (and its traceback) can name hosts, paths or upstream providers; it goes to the log, where the
    id in ``X-Correlation-Id`` finds the exact line. Callers write ``raise _internal_error(e, 'predict')``."""
    cid = uuid.uuid4().hex[:12]
    logger.error('%s failed (correlation %s): %s', where, cid, exc, exc_info=True)
    return HTTPException(status_code=500, detail=detail, headers={'X-Correlation-Id': cid})


# ---------- بارگذاری مدل PyTorch ----------
MODEL_DIR = Path(__file__).parent / "models"
model_path = MODEL_DIR / "student_risk_model.pth"
scaler_path = MODEL_DIR / "scaler.joblib"

if not model_path.exists() or not scaler_path.exists():
    raise RuntimeError("مدل یا scaler وجود ندارد. لطفاً train_nn_model.py را اجرا کنید.")

scaler = joblib.load(scaler_path)
input_dim = len(scaler.mean_)
risk_model = StudentRiskModel(input_dim=input_dim)
# weights_only: tensors only, no pickled code (S-11); supported since torch 1.13
risk_model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu'), weights_only=True))
risk_model.eval()
logger.info("✅ مدل پیش‌بینی ریسک با موفقیت بارگذاری شد.")

# ---------- راه‌اندازی FastAPI و جدول اسناد ----------
app = FastAPI(title="School AI Platform", description="سرویس یکپارچه هوش مصنوعی مدرسه", version="2.0.0")

@app.on_event("startup")
async def startup():
    validate_service_secret()  # fail before serving traffic if the service-token secret is unusable
    # FastAPI never creates or alters the schema: Django migrations own it (ADR-0001).
    # This is a read-only check so a missing table is visible in the logs.
    try:
        if documents_table_exists():
            logger.info("Table 'documents' found.")
        else:
            logger.error("Table 'documents' is missing. Run Django migrations (python manage.py migrate).")
    except Exception as e:
        logger.error(f"Could not check 'documents' table: {e}")

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
def _single_school(payload: dict) -> int:
    """The one school a document is stored for (ingestion is disabled in Phase 1; a token with several schools must choose)."""
    ids = school_ids(payload)
    if len(ids) != 1:
        raise HTTPException(status_code=403, detail="Exactly one school is required.")
    return ids[0]


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
@router_v1.post("/predict/")
async def predict_risk(features: StudentFeatures, payload: dict = Depends(require_roles(ADMIN))):  # Teacher excluded until teacher->student assignment exists (S-04)
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
        raise _internal_error(e, 'predict')
app.include_router(router_v1)

class LLMRequest(BaseModel):
    purpose: str = Field(max_length=40)
    messages: list[dict[str, str]] = Field(max_length=20)
    avoid_names: list[str] = Field(default=[], max_length=2000)   # roster names that must not leave the platform (external class); ONLY Django may send this route a request (see AI_GOVERNANCE)


_LLM_STATUS = {"bad_request": 422, "purpose_refused": 422, "pii_refused": 422, "not_configured": 503, "bad_config": 503,
               "cap_reached": 429, "busy": 429, "upstream_error": 502}


LLM_ROLES = (ADMIN, TEACHER, "GradeLead", "Counselor")      # staff only; Django adds the one-school claim for them (service_headers(with_school=...))


@app.get("/llm/status/")
def llm_status(payload: dict = Depends(require_roles_with_schools(*LLM_ROLES, ai_scope_ok=True))):
    """Which provider CLASS (if any) is active for the caller's one school; no URL, model or key."""
    school = _single_school(payload)
    try:
        provider = llm_adapter.provider_for_school(school)
    except llm_adapter.LLMError:
        return {"enabled": False, "class": None}
    return {"enabled": provider is not None, "class": provider.kind if provider else None}


@app.post("/llm/complete/")
def llm_complete(request: LLMRequest, http: Request, payload: dict = Depends(require_roles_with_schools(*LLM_ROLES, ai_scope_ok=True))):
    """P7 staff assistant call (provider-agnostic, OFF unless an operator maps the school to a provider). The caller's school comes from
    the signed token, never from the body; Django applies ACL BEFORE building the messages and enforces the licensed per-school caps."""
    school = _single_school(payload)
    if int(http.headers.get("content-length") or 0) > 200_000:
        raise HTTPException(status_code=413, detail="bad_request")
    try:
        provider = llm_adapter.provider_for_school(school)
        if provider is None:
            raise HTTPException(status_code=403, detail="AI is not enabled for this school.")
        names = [n[:100] for n in request.avoid_names]
        return llm_adapter.complete(provider, request.messages, request.purpose, school_id=school, roster_names=names)
    except llm_adapter.LLMError as exc:
        raise HTTPException(status_code=_LLM_STATUS.get(exc.code, 502), detail=exc.code)


@app.post("/chat/")
async def chat_endpoint(request: ChatRequest, payload: dict = Depends(disabled_in_phase1)):  # RAG out of Phase 1 scope
    try:
        result = chat(request.query, school_ids(payload))   # ACL before retrieval (route disabled in Phase 1)
        return result
    except Exception as e:
        raise _internal_error(e, 'chat')

@app.post("/documents/")
async def add_document_endpoint(request: DocumentRequest, payload: dict = Depends(disabled_in_phase1)):  # ingestion disabled: no embedding model
    try:
        add_document(request.title, request.content, school_id=_single_school(payload), metadata=request.metadata)
        return {"status": "success", "message": "سند با موفقیت اضافه شد."}
    except Exception as e:
        raise _internal_error(e, 'add_document')

@app.get("/documents/list/")
async def list_documents(payload: dict = Depends(require_roles_with_schools(ADMIN))):  # only the caller's schools (token claim)
    # فقط کاربران احراز هویت شده می‌توانند لیست اسناد را مشاهده کنند
    try:
        docs = get_all_documents(payload["schools"])
        return {"documents": docs}
    except Exception as e:
        raise _internal_error(e, 'list_documents')

@app.get("/documents/search/")
async def search_documents_endpoint(query: str, top_k: int = 3, payload: dict = Depends(disabled_in_phase1)):  # embedding-based; RAG out of Phase 1 scope
    try:
        results = search_documents(query, top_k, school_ids(payload))
        return {
            "results": [
                {"title": r[0], "content": r[1][:200] + "...", "similarity": r[3]}
                for r in results
            ]
        }
    except Exception as e:
        raise _internal_error(e, 'search_documents')

@app.post("/upload-document/", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...), payload: dict = Depends(disabled_in_phase1)):  # ingestion disabled: no embedding model
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
            add_documents_batch(documents_to_add, school_id=_single_school(payload))

        logger.info(f"فایل {file.filename} با موفقیت پردازش شد. تعداد قطعات: {len(chunks)}")

        return UploadResponse(
            status="success",
            message=f"فایل با موفقیت بارگذاری شد و به {len(chunks)} بخش تقسیم شد.",
            chunks=len(chunks)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e, 'upload_document')

@app.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: int, payload: dict = Depends(require_roles_with_schools(ADMIN))):
    try:
        deleted = delete_document(doc_id, payload["schools"])   # 404 also for another school's document
        if deleted:
            return {"status": "success", "message": "سند با موفقیت حذف شد."}
        else:
            raise HTTPException(status_code=404, detail="سند پیدا نشد.")
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e, 'delete_document', detail='Internal error while deleting the document.')

@app.delete("/documents/parent/{parent_id}")
async def delete_document_by_parent_endpoint(parent_id: str, payload: dict = Depends(require_roles_with_schools(ADMIN))):
    try:
        deleted = delete_document_by_parent_id(parent_id, payload["schools"])
        if deleted:
            return {"status": "success", "message": "فایل با موفقیت حذف شد."}
        else:
            raise HTTPException(status_code=404, detail="فایل پیدا نشد.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"خطا در حذف فایل: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while deleting the file.")