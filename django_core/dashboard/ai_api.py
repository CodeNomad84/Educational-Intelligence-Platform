"""JSON AI chat/status for the mentor assistant («رهنما») in the presentation frontends.

Two endpoints under ``/api/ai/``:

* ``GET  /api/ai/status/`` — health check for the mentor chat: the mentor personas the caller may use,
  whether the ``advisor_ai`` module is on for the caller's school, whether AI features are enabled, and
  whether the FastAPI LLM reports a configured provider for the school.
* ``POST /api/ai/chat/``  — one mentor chat turn. The requested persona is checked against the caller's REAL
  roles on the server (403 on mismatch). The question is screened for student data and then sent to the
  FastAPI LLM with the non-personal ``pedagogy`` purpose; no roster, no notes and no school data are ever
  placed in the prompt.

Governance (docs/AI_GOVERNANCE.md): external LLMs may only receive non-personal content. This endpoint uses
the ``pedagogy`` purpose (allowed for both provider classes) and never forwards ``recentNotes`` or any student
record. The caller's school comes from the signed service token (``service_headers``), never from the request.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import requests
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from config.service_auth import service_headers
from docqa.screen import screen_text
from schools import ai_guard
from schools.entitlements import ADVISOR_AI, module_enabled, user_school_ids
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER, roles_for

MENTOR_ROLE_KEYS = ("teacher", "counselor", "principal")
# Django role group(s) that grant each mentor persona. A Grade Lead coaches through the teacher persona.
MENTOR_ROLE_GROUPS = {
    "teacher": (TEACHER, GRADE_LEAD),
    "counselor": (COUNSELOR,),
    "principal": (ADMIN,),
}
MODULE = ADVISOR_AI
SYSTEM_PROMPT = (
    "You are a school mentoring and growth assistant for teachers, counselors and school principals. "
    "Answer in Persian, briefly and practically. Never invent student names, numbers or school data; "
    "when a question needs school data you do not have, say so and ask for the information."
)

MESSAGES_MAX = 24
MESSAGE_MAX_CHARS = 8000

DETAIL = {
    "no_role": "حساب شما به دستیار مربیگری دسترسی ندارد.",
    "ai_disabled": "ابزار هوش مصنوعی فعال نیست.",
    "module_locked": "ماژول دستیار هوش مصنوعی برای مدرسهٔ شما قفل است.",
    "key_not_set": "کلید API یا مدل زبانی برای مدرسهٔ شما تنظیم نشده است.",
    "service_unavailable": "سرویس هوش مصنوعی در دسترس نیست.",
}

# Codes FastAPI's /llm/complete/ returns (fastapi_core/llm_adapter.py) -> (HTTP status, Persian message).
LLM_ERROR_STATUS = {
    "not_configured": (status.HTTP_503_SERVICE_UNAVAILABLE, "کلید API مدل زبانی تنظیم نشده است."),
    "bad_config": (status.HTTP_503_SERVICE_UNAVAILABLE, "تنظیمات مدل زبانی نادرست است."),
    "upstream_error": (status.HTTP_502_BAD_GATEWAY, "سرویس هوش مصنوعی در دسترس نیست."),
    "busy": (status.HTTP_429_TOO_MANY_REQUESTS, "سرویس هوش مصنوعی در حال حاضر مشغول است؛ کمی بعد دوباره تلاش کنید."),
    "cap_reached": (status.HTTP_429_TOO_MANY_REQUESTS, "سقف استفاده از دستیار هوشمند برای مدرسه پر شده است."),
    "purpose_refused": (status.HTTP_422_UNPROCESSABLE_ENTITY, "این درخواست برای دستیار مربیگری مجاز نیست."),
    "pii_refused": (status.HTTP_422_UNPROCESSABLE_ENTITY, "این درخواست برای دستیار مربیگری مجاز نیست."),
    "bad_request": (status.HTTP_422_UNPROCESSABLE_ENTITY, "درخواست نامعتبر است."),
    "service_unavailable": (status.HTTP_503_SERVICE_UNAVAILABLE, "سرویس هوش مصنوعی در دسترس نیست."),
}


def service_url(path):
    """The ONE FastAPI address (change 0044 / E2E F03): settings.FASTAPI_BASE_URL + the route path."""
    return f"{settings.FASTAPI_BASE_URL}{path}"


def mentor_roles_for(user):
    """Mentor personas the user may use, in display order."""
    roles = roles_for(user)
    return [key for key in MENTOR_ROLE_KEYS if roles & set(MENTOR_ROLE_GROUPS[key])]


def _staff_schools(user, module_on=True):
    """Schools the user may use the mentor assistant for (staff memberships only, never parent/student links)."""
    from schools.models import SchoolStaff
    from students.access import school_ids_for_admin

    staff = set(school_ids_for_admin(user)) | set(
        SchoolStaff.objects.filter(user=user).values_list("school_id", flat=True)
    )
    ids = sorted(staff & user_school_ids(user))
    if module_on:
        ids = [sid for sid in ids if module_enabled(sid, MODULE)]
    return ids


def _llm_status(headers):
    """``{enabled, class}`` from FastAPI, or ``None`` when the service is unreachable/misconfigured."""
    try:
        response = requests.get(service_url("/llm/status/"), headers=headers, timeout=3)
        body = response.json() if response.status_code == 200 else None
        return body if isinstance(body, dict) else None
    except (requests.RequestException, ValueError):
        return None


class _LLMUnavailable(Exception):
    """A refused/failed LLM call with a fixed code (never a key, URL or provider text)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _llm_complete(headers, messages):
    try:
        response = requests.post(
            service_url("/llm/complete/"),
            json={"purpose": "pedagogy", "messages": messages},
            headers=headers,
            timeout=65,
        )
    except requests.RequestException:
        raise _LLMUnavailable("service_unavailable") from None
    if response.status_code != 200:
        code = "service_unavailable"
        try:
            detail = response.json().get("detail")
            if isinstance(detail, str) and detail in LLM_ERROR_STATUS:
                code = detail
        except (ValueError, AttributeError):
            pass
        raise _LLMUnavailable(code)
    try:
        return response.json()
    except ValueError:
        raise _LLMUnavailable("service_unavailable") from None


def _validated_messages(payload):
    """Return the cleaned user/assistant message list, or ``None`` (caller answers 400)."""
    messages = payload.get("messages")
    if not isinstance(messages, list) or not (1 <= len(messages) <= MESSAGES_MAX):
        return None
    clean = []
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            return None
        if message.get("role") not in ("user", "assistant") or not isinstance(message.get("content"), str):
            return None
        content = message["content"].strip()
        if not content or len(content) > MESSAGE_MAX_CHARS:
            return None
        clean.append({"role": message["role"], "content": content})
    return clean


class AIStatusView(APIView):
    authentication_classes = (JWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        roles = mentor_roles_for(user)
        if not roles:
            return Response({"enabled": False, "reason": "no_role", "detail": DETAIL["no_role"], "roles": roles})
        if not getattr(settings, "ENABLE_AI_FEATURES", False):
            return Response(
                {"enabled": False, "reason": "ai_disabled", "detail": DETAIL["ai_disabled"], "roles": roles}
            )
        schools = _staff_schools(user, module_on=True)
        if not schools:
            return Response(
                {"enabled": False, "reason": "module_locked", "detail": DETAIL["module_locked"], "roles": roles}
            )
        try:
            headers = service_headers(user, with_school=schools[0])
        except ImproperlyConfigured:
            return Response(
                {"enabled": False, "reason": "service_unavailable", "detail": DETAIL["service_unavailable"],
                 "roles": roles}
            )
        llm = _llm_status(headers)
        if llm is None:
            return Response(
                {"enabled": False, "reason": "service_unavailable", "detail": DETAIL["service_unavailable"],
                 "roles": roles}
            )
        if not llm.get("enabled"):
            return Response(
                {"enabled": False, "reason": "key_not_set", "detail": DETAIL["key_not_set"], "roles": roles}
            )
        return Response({"enabled": True, "reason": None, "detail": None, "roles": roles})


class AIChatView(APIView):
    authentication_classes = (JWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.user
        payload = request.data if isinstance(request.data, dict) else {}
        role = payload.get("role")
        if role not in MENTOR_ROLE_GROUPS:
            return Response({"detail": "نقش نامعتبر است.", "code": "bad_role"}, status=status.HTTP_400_BAD_REQUEST)
        # Server-side role check: the requested persona must be one the caller actually holds.
        if not (roles_for(user) & set(MENTOR_ROLE_GROUPS[role])):
            return Response(
                {"detail": "این نقش با نقش واقعی شما هماهنگ نیست.", "code": "role_mismatch"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not getattr(settings, "ENABLE_AI_FEATURES", False):
            return Response(
                {"detail": DETAIL["ai_disabled"], "code": "ai_disabled"}, status=status.HTTP_403_FORBIDDEN
            )
        schools = _staff_schools(user, module_on=True)
        if not schools:
            return Response(
                {"detail": DETAIL["module_locked"], "code": "module_locked"}, status=status.HTTP_403_FORBIDDEN
            )
        school_id = schools[0]

        messages = _validated_messages(payload)
        if messages is None:
            return Response(
                {"detail": "پیام نامعتبر است.", "code": "bad_request"}, status=status.HTTP_400_BAD_REQUEST
            )
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if screen_text(last_user, school_id):
            return Response(
                {"detail": "سؤال نباید نام، شناسه یا شمارهٔ تماس دانش‌آموز داشته باشد.", "code": "pii_refused"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            headers = service_headers(user, with_school=school_id)
        except ImproperlyConfigured:
            return Response(
                {"detail": DETAIL["service_unavailable"], "code": "service_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            ai_guard.consume(school_id, MODULE)
        except ai_guard.AICapReached as cap:
            return Response({"detail": cap.message_fa, "code": "cap_reached"},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        try:
            out = _llm_complete(headers, [{"role": "system", "content": SYSTEM_PROMPT}, *messages])
        except _LLMUnavailable as exc:
            ai_guard.refund(school_id, MODULE)      # F05: a call that delivered no answer must not burn the cap
            code = exc.code if exc.code in LLM_ERROR_STATUS else "service_unavailable"
            http_status, detail = LLM_ERROR_STATUS[code]
            return Response({"detail": detail, "code": code}, status=http_status)
        return Response({
            "text": out.get("text", ""),
            "label": out.get("label", ""),
            "provider_class": out.get("provider_class", ""),
        })
