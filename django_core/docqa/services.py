"""Document assistant pipeline (P7-5). ACL first: retrieval reads only the caller's school and active documents. The prompt contains
ONLY the question and numbered excerpts of those documents (no student data; the question is screened). A call is made only if the
school setting is on AND FastAPI reports a LOCAL provider for the school AND the daily/monthly cap allows; otherwise the user gets the
retrieved excerpts (a plain document search). Audit rows carry counts and codes, never the question or the answer."""
import math
import re
from collections import Counter

import requests
from django.db import transaction

from config.service_auth import service_headers
from schools import ai_guard, audit

from .extract import ExtractError, extract_text
from .models import AssistantSettings, DocumentChunk, SchoolDocument
from .screen import normalize, screen_text

FASTAPI = 'http://fastapi:8001'
CHUNK_CHARS, TOP_K, MAX_QUESTION = 900, 4, 500
STOP = {'و', 'در', 'به', 'از', 'که', 'را', 'این', 'آن', 'با', 'برای', 'است', 'شد', 'شود', 'می', 'یا', 'تا', 'بر', 'هم', 'یک', 'های', 'ها'}
TOKEN = re.compile(r'[\w]+', re.U)
CITE = re.compile(r'\[(\d{1,2})\]')
SYSTEM_PROMPT = ('You answer questions for school staff ONLY from the numbered excerpts of the school documents below. '
                 'If the answer is not in the excerpts, say that you cannot find it in the documents. Cite the excerpt numbers like [1]. '
                 'Answer in Persian, briefly. Never invent rules, names or numbers.')


class AskRefused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def chunk_text(text, size=CHUNK_CHARS):
    chunks, buf = [], ''
    for para in re.split(r'\n\s*\n', text):
        para = para.strip()
        while len(para) > size:               # a very long paragraph is cut at a space near the limit
            cut = para.rfind(' ', 0, size) or size
            cut = cut if cut > size // 2 else size
            if buf:
                chunks.append(buf)
                buf = ''
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        if not para:
            continue
        if buf and len(buf) + len(para) + 2 > size:
            chunks.append(buf)
            buf = ''
        buf = f'{buf}\n\n{para}' if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def tokens(text):
    return [t for t in TOKEN.findall(normalize(text)) if len(t) > 1 and t not in STOP]


@transaction.atomic
def add_document(user, school_id, title, filename, data):
    """Create a document from an upload. Raises ``ExtractError`` / ``AskRefused('screen:...')`` with fixed codes."""
    text = extract_text(filename, data)
    reasons = screen_text(text, school_id)
    if reasons:
        raise AskRefused('screen:' + ','.join(reasons))
    doc = SchoolDocument.objects.create(school_id=school_id, title=title, source_name=(filename or '')[:200], char_count=len(text),
                                        uploaded_by=user)
    DocumentChunk.objects.bulk_create([DocumentChunk(document=doc, school_id=school_id, ordinal=i, text=c)
                                       for i, c in enumerate(chunk_text(text))])
    return doc


def retrieve(school_id, question, k=TOP_K):
    """Top ``k`` excerpts of the school's ACTIVE documents (BM25-like). Reads only ``school_id`` rows; nothing else is reachable."""
    query = tokens(question)
    if not query:
        return []
    rows = list(DocumentChunk.objects.filter(school_id=school_id, document__is_active=True).select_related('document'))
    if not rows:
        return []
    counts = [Counter(tokens(r.text)) for r in rows]
    avg = sum(sum(c.values()) for c in counts) / len(rows) or 1
    df = Counter(t for c in counts for t in c)
    scored = []
    for row, c in zip(rows, counts):
        length = sum(c.values()) or 1
        score = 0.0
        for t in set(query):
            if c[t]:
                idf = math.log(1 + (len(rows) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * c[t] * 2.2 / (c[t] + 1.2 * (0.25 + 0.75 * length / avg))
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    return [r for _s, r in scored[:k]]


def _local_provider_active(headers):
    try:
        r = requests.get(f'{FASTAPI}/llm/status/', headers=headers, timeout=3)
        return r.status_code == 200 and r.json().get('enabled') and r.json().get('class') == 'local'
    except (requests.RequestException, ValueError):
        return False


def _complete(headers, excerpts, question):
    context = '\n\n'.join(f'[{i}] ({e.document.title}) {e.text}' for i, e in enumerate(excerpts, 1))
    body = {'purpose': 'document_qa', 'messages': [{'role': 'system', 'content': SYSTEM_PROMPT},
                                                  {'role': 'user', 'content': f'Excerpts:\n{context}\n\nQuestion: {question}'}]}
    r = requests.post(f'{FASTAPI}/llm/complete/', json=body, headers=headers, timeout=65)
    if r.status_code != 200:
        raise AskRefused(f'llm_{r.status_code}')
    return r.json()


def ask(user, school, question):
    """Returns ``{mode: 'ai'|'search'|'none', answer, label, excerpts, cited, notice}``; raises ``AskRefused`` for a refused question."""
    question = (question or '').strip()
    if not question or len(question) > MAX_QUESTION:
        raise AskRefused('bad_question')
    if screen_text(question, school.pk):
        audit.record(user, audit.DOC_ASK, school=school.pk, detail='refused:screen')
        raise AskRefused('screen')
    excerpts = retrieve(school.pk, question)
    if not excerpts:
        audit.record(user, audit.DOC_ASK, school=school.pk, detail='none')
        return {'mode': 'none', 'excerpts': [], 'cited': [], 'notice': ''}
    result = {'mode': 'search', 'excerpts': excerpts, 'cited': [], 'answer': '', 'label': '', 'notice': ''}
    settings = AssistantSettings.objects.filter(school=school).first()
    if not (settings and settings.ai_enabled):
        audit.record(user, audit.DOC_ASK, school=school.pk, detail=f'search:k{len(excerpts)}')
        return result
    headers = service_headers(user, with_school=school.pk)
    if not _local_provider_active(headers):
        result['notice'] = 'مدل زبانی محلی برای این مدرسه فعال نیست؛ بخش‌های مرتبط سند نمایش داده می‌شود.'
        audit.record(user, audit.DOC_ASK, school=school.pk, detail=f'search:k{len(excerpts)}:nolocal')
        return result
    try:
        ai_guard.consume(school, 'advisor_ai')
    except ai_guard.AICapReached as cap:
        result['notice'] = cap.message_fa
        audit.record(user, audit.DOC_ASK, school=school.pk, detail=f'search:k{len(excerpts)}:cap')
        return result
    try:
        out = _complete(headers, excerpts, question)
    except (requests.RequestException, ValueError, AskRefused):
        result['notice'] = 'پاسخ هوشمند در دسترس نبود؛ بخش‌های مرتبط سند نمایش داده می‌شود.'
        audit.record(user, audit.DOC_ASK, school=school.pk, detail=f'search:k{len(excerpts)}:error')
        return result
    cited = sorted({int(n) for n in CITE.findall(out['text']) if 1 <= int(n) <= len(excerpts)})
    result.update(mode='ai', answer=out['text'], label=out.get('label', ''), cited=cited)
    if not cited:
        result['notice'] = 'پاسخ به هیچ بخشی از سند ارجاع نداده است؛ قابل اعتماد نیست. بخش‌های مرتبط را ببینید.'
    audit.record(user, audit.DOC_ASK, school=school.pk, detail=f'ai:k{len(excerpts)}c{len(cited)}')
    return result
