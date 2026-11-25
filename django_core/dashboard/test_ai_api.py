"""Mentor assistant JSON endpoints (dashboard/ai_api.py) — role mapping, module gate and LLM availability.

Synthetic accounts only; the FastAPI leg is mocked (``requests`` + ``service_headers``), so no network or secret
is needed. The role check is exercised for real: a persona the caller does not hold is a 403.
"""
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from schools.models import School, SchoolClass, SchoolMembership, SchoolModule, SchoolStaff
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, TEACHER
from students.models import Student

User = get_user_model()
PASSWORD = "Str0ng-demo-pass-77"
MSG = {"role": "teacher", "messages": [{"role": "user", "content": "چطور کار گروهی را در کلاس تقویت کنم؟"}]}


class AIApiBase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school = School.objects.create(name="A", code="a")
        self.status_url = reverse("api_ai_status")
        self.chat_url = reverse("api_ai_chat")

    def user_with(self, role, *, admin=False):
        user = User.objects.create_user(f"u{User.objects.count():08d}", password=PASSWORD)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        if admin:
            SchoolMembership.objects.create(user=user, school=self.school)
        else:
            SchoolStaff.objects.create(user=user, school=self.school)
        return user

    def enable_module(self):
        SchoolModule.objects.create(
            school=self.school, module_key="advisor_ai", kind="licensed",
            starts_on=date.today() - timedelta(days=1), ends_on=None,
        )

    def login(self, user):
        self.client.force_login(user)


class StatusTests(AIApiBase):
    def test_anonymous_is_401(self):
        self.assertEqual(self.client.get(self.status_url).status_code, 401)

    def test_no_mentor_role_is_no_role(self):
        user = User.objects.create_user("parent0001", password=PASSWORD)
        user.groups.add(Group.objects.get_or_create(name=PARENT)[0])
        self.login(user)
        body = self.client.get(self.status_url).json()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["reason"], "no_role")
        self.assertEqual(body["roles"], [])

    def test_teacher_maps_to_teacher_persona(self):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        body = self.client.get(self.status_url).json()
        self.assertEqual(body["roles"], ["teacher"])

    def test_admin_maps_to_principal_persona(self):
        self.enable_module()
        self.login(self.user_with(ADMIN, admin=True))
        body = self.client.get(self.status_url).json()
        self.assertEqual(body["roles"], ["principal"])

    def test_multiple_roles_show_every_persona_held(self):
        self.enable_module()
        user = User.objects.create_user("multi0001", password=PASSWORD)
        user.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        user.groups.add(Group.objects.get_or_create(name=COUNSELOR)[0])
        SchoolStaff.objects.create(user=user, school=self.school)
        self.login(user)
        self.assertEqual(self.client.get(self.status_url).json()["roles"], ["teacher", "counselor"])

    def test_module_locked(self):
        self.login(self.user_with(TEACHER))
        body = self.client.get(self.status_url).json()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["reason"], "module_locked")

    @override_settings(ENABLE_AI_FEATURES=False)
    def test_ai_features_off(self):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        body = self.client.get(self.status_url).json()
        self.assertEqual(body["reason"], "ai_disabled")

    @mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"})
    def test_llm_not_mapped_is_key_not_set(self, _sh):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        with mock.patch("dashboard.ai_api.requests.get") as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: {"enabled": False, "class": None})
            body = self.client.get(self.status_url).json()
        self.assertEqual(body["reason"], "key_not_set")

    @mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"})
    def test_service_down_is_service_unavailable(self, _sh):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        with mock.patch("dashboard.ai_api.requests.get", side_effect=__import__("requests").RequestException):
            body = self.client.get(self.status_url).json()
        self.assertEqual(body["reason"], "service_unavailable")

    @mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"})
    def test_enabled_when_llm_available(self, _sh):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        with mock.patch("dashboard.ai_api.requests.get") as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: {"enabled": True, "class": "local"})
            body = self.client.get(self.status_url).json()
        self.assertTrue(body["enabled"])
        self.assertIsNone(body["reason"])
        self.assertEqual(body["roles"], ["teacher"])


class ChatTests(AIApiBase):
    def test_anonymous_is_401(self):
        self.assertEqual(
            self.client.post(self.chat_url, MSG, content_type="application/json").status_code, 401
        )

    def test_role_mismatch_is_403(self):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        body = {"role": "principal", "messages": MSG["messages"]}
        resp = self.client.post(self.chat_url, body, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "role_mismatch")

    def test_module_locked_is_403(self):
        self.login(self.user_with(TEACHER))
        resp = self.client.post(self.chat_url, MSG, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "module_locked")

    def test_invalid_role_is_400(self):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        resp = self.client.post(
            self.chat_url, {"role": "owner", "messages": MSG["messages"]}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    @mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"})
    @mock.patch("dashboard.ai_api.ai_guard.consume")
    def test_success_returns_llm_text(self, _consume, _sh):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        with mock.patch("dashboard.ai_api.requests.post") as post:
            post.return_value = mock.Mock(
                status_code=200,
                json=lambda: {"text": "پاسخ", "label": "برچسب", "provider_class": "local"},
            )
            resp = self.client.post(self.chat_url, MSG, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["text"], "پاسخ")
        self.assertEqual(resp.json()["provider_class"], "local")

    @mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"})
    @mock.patch("dashboard.ai_api.ai_guard.consume")
    @mock.patch("dashboard.ai_api.ai_guard.refund")
    def test_upstream_error_is_502_and_refunded(self, _refund, _consume, _sh):
        self.enable_module()
        self.login(self.user_with(TEACHER))
        with mock.patch("dashboard.ai_api.requests.post") as post:
            post.return_value = mock.Mock(status_code=502, json=lambda: {"detail": "upstream_error"})
            resp = self.client.post(self.chat_url, MSG, content_type="application/json")
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.json()["code"], "upstream_error")
        self.assertTrue(_refund.called)

    def test_question_with_student_name_is_refused(self):
        self.enable_module()
        teacher = self.user_with(TEACHER)
        klass = SchoolClass.objects.create(school=self.school, title="7A", grade=7)
        Student.objects.create(
            first_name="یاسین", last_name="عباسی", national_id="0012345678", grade=7,
            phone_number="1", school=self.school, school_class=klass,
        )
        self.login(teacher)
        body = {"role": "teacher", "messages": [{"role": "user", "content": "یاسین عباسی چطور است؟"}]}
        with mock.patch("dashboard.ai_api.service_headers", return_value={"Authorization": "Bearer x"}):
            resp = self.client.post(self.chat_url, body, content_type="application/json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "pii_refused")
