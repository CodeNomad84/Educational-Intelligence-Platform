# students/views.py
import re
import pandas as pd
from io import BytesIO, TextIOWrapper
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from collections import defaultdict, namedtuple
from django.db import transaction
from django.db.models import ProtectedError
from .models import Student
from django.db.models import Avg
from schools.models import School, SchoolClass
from .class_resolution import (
    AMBIGUOUS, CLASS_BLANK, NO_UNIQUE_SCHOOL, UNMATCHED_STATUSES, ClassCandidate, Resolution,
    apply_grade_guard, resolve_class,
)
import requests
from .serializers import StudentSerializer, FileUploadSerializer
from .student_school import NATIONAL_ID_REFUSED, StudentSchoolError, resolve_student_school
from .permissions import IsAdminUser  # فقط ادمین بتواند آپلود کند
from django.core.exceptions import ImproperlyConfigured
from config.service_auth import service_headers
from . import import_store
from .enrollment_sync import ensure_current_enrollment
from schools import audit
from .access import search_students, visible_attendances, visible_grades, visible_students

# --- student import: class resolution (C3c-2) -------------------------------------------------------------
# The import never creates or changes a School or SchoolClass and never overwrites or clears an existing
# Student.school_class. Decisions are taken for the WHOLE file before any NEW link is written, and on
# PERSISTED state: the rows of students that already have a class are written first (they never carry a link
# change), so a failed write cannot leave the guard working with a grade that was never stored. Decisions do
# not depend on row order. See students/class_resolution.py for the decision rules.
IMPORT_CHUNK = 500
UNMATCHED_LIST_LIMIT = 200
UNMATCHED_VALUE_MAX = 100
# H-1 (T7): a real roster is a few tens of KB; 2 MB is ≳10 000 rows of this schema and is the same ceiling the school
# bulk-account upload already uses (dashboard/bulk_accounts.MAX_FILE_BYTES). A module constant, not a setting: this is a
# resource guard, not a school preference (decision D1=a).
IMPORT_MAX_BYTES = 2 * 1024 * 1024
IMPORT_TOO_LARGE = 'حجم فایل بیش از حد مجاز است (حداکثر ۲ مگابایت).'

ImportRow = namedtuple('ImportRow', 'index national_id data class_cell')

# Columns read as text so identifiers keep their exact form (a blank cell must not turn the column to float
# text, and leading zeros must survive). Only these columns: grade and class_name keep pandas' inference.
TEXT_COLUMNS = {'national_id': str, 'phone_number': str}

NATIONAL_ID_MAX_LENGTH = 10   # mirrors Student.national_id max_length
_NAN_LIKE = {'nan', 'none', 'null'}
_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _bounded_upload(file):
    """The bytes of an upload, or ``None`` when it exceeds ``IMPORT_MAX_BYTES`` (H-1).

    The declared ``size`` is checked first, so an honest oversized upload is refused without a read; the bounded read
    is what actually enforces the ceiling, because a request can understate (or omit) its size. At most
    ``IMPORT_MAX_BYTES + 1`` bytes are ever held in memory, whatever the upload claims to be."""
    if (getattr(file, 'size', 0) or 0) > IMPORT_MAX_BYTES:
        return None
    payload = file.read(IMPORT_MAX_BYTES + 1)
    return None if len(payload) > IMPORT_MAX_BYTES else payload


def _clean_national_id(value):
    """Return ``(national_id, error)``; exactly one of them is empty. Import path only (ASCII digits out)."""
    if value is None or (isinstance(value, float) and value != value):
        return '', 'کد ملی خالی است.'
    text = str(value).strip().translate(_DIGIT_MAP)
    if not text:
        return '', 'کد ملی خالی است.'
    if text.lower() in _NAN_LIKE or re.fullmatch(r'[0-9]+\.0+', text):
        return '', 'کد ملی معتبر نیست.'
    if not re.fullmatch(r'[0-9]+', text):
        return '', 'کد ملی باید فقط شامل ارقام باشد.'
    if len(text) > NATIONAL_ID_MAX_LENGTH:
        return '', 'کد ملی نباید بیش از ۱۰ رقم باشد.'
    return text, ''



class ImportSchoolConflict(Exception):
    """The national id belongs to a student of ANOTHER school. The message is fixed and generic on purpose: it must
    not tell the importer anything about that student or school (national_id is still globally unique until S7)."""

    MESSAGE = NATIONAL_ID_REFUSED

    def __init__(self):
        super().__init__(self.MESSAGE)


class ClassLinkPlan:
    def __init__(self, school_id):
        # The school every row of this import belongs to (S2b: resolved ONCE from the importing user's memberships /
        # the explicit target, never from the file and never from "the only School").
        self.school_id = school_id
        self.decisions = {}                        # row index -> SchoolClass pk to link
        self.preserved_links = 0                   # existing students whose link was left untouched
        self.class_blank = 0                       # eligible rows with a blank class cell
        self.unmatched = []                        # {'row', 'value', 'reason'}, file order, uncapped


def _chunks(items, size=IMPORT_CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _linked_national_ids(rows, school_id):
    """National ids (among ``rows``) of students OF THE IMPORT SCHOOL that already have a class link."""
    return import_store.linked_national_ids(school_id, {r.national_id for r in rows})


def _plan_class_links(rows, school_id):
    """Decide, for every valid row, whether its student may be linked to an existing class.

    Must run AFTER the rows of already-linked students were written: member grades are read from the
    database, i.e. they are the grades that were really persisted."""
    school_ids = [school_id]
    plan = ClassLinkPlan(school_id)
    candidates = [ClassCandidate.from_model(c) for c in SchoolClass.objects.filter(school_id=school_id)]

    # students of the import school only: a national id of another school is invisible here and is refused at write
    existing = {nid: (school_id, class_id)
                for nid, class_id in import_store.existing_state(school_id, {r.national_id for r in rows}).items()}
    # (a candidate class is always a class of the import school, so a link can never leave the school)

    by_student = defaultdict(list)
    for row in rows:
        by_student[row.national_id].append(row)

    resolutions = {}   # row index -> Resolution (eligible rows only)
    eligible = []
    for nid, student_rows in by_student.items():
        state = existing.get(nid)
        if state is not None and state[1] is not None:   # already linked: immutable, uploaded class ignored
            plan.preserved_links += 1
            continue
        per_row = []
        for row in student_rows:
            res = resolve_class(row.class_cell, school_ids=school_ids, candidates=candidates)
            per_row.append((row, res))
        if len({res.candidate.pk for _row, res in per_row if res.resolved}) > 1:
            # duplicate rows of one student naming different classes: no order-dependent pick
            per_row = [(row, Resolution(AMBIGUOUS, title=res.title) if res.resolved else res)
                       for row, res in per_row]
        for row, res in per_row:
            resolutions[row.index] = res
            eligible.append(row)

    eligible.sort(key=lambda r: r.index)
    # Grades of the members of every class an incoming row resolved to, as PERSISTED. Members that appear in
    # this file were written before this call, so a successful change is already visible here and a failed
    # one is not assumed.
    targets = {res.candidate.pk for res in resolutions.values() if res.resolved}
    existing_grades = defaultdict(list, import_store.grades_by_class(school_id, targets))

    final = apply_grade_guard([(resolutions[r.index], r.data['grade']) for r in eligible], existing_grades)
    for row, res in zip(eligible, final):
        if res.resolved:
            plan.decisions[row.index] = res.candidate.pk
        elif res.status == CLASS_BLANK:
            plan.class_blank += 1
        elif res.status in UNMATCHED_STATUSES:
            plan.unmatched.append({'row': row.index + 2, 'value': res.title[:UNMATCHED_VALUE_MAX],
                                   'reason': res.status})
    return plan


def _write_import_row(row, plan):
    """Pass 3 for one row: the existing update_or_create, plus school/class only where it is safe NOW."""
    with transaction.atomic():
        # Row lock where the database supports it (PostgreSQL); a no-op on SQLite. It also re-reads the
        # student's link state at write time, so a link created meanwhile is never overwritten.
        current = import_store.locked_state(row.national_id)
        if current is not None and current['school_id'] != plan.school_id:
            # another school's student, or a legacy student WITHOUT a school: never overwritten, moved or adopted here
            # (S6: only ``backfill_student_school`` gives an existing student a school)
            raise ImportSchoolConflict()
        defaults = dict(row.data)
        class_pk = plan.decisions.get(row.index)
        link = False
        if current is None or current['school_class_id'] is None:
            defaults['school_id'] = plan.school_id
            if class_pk is not None:
                defaults['school_class_id'] = class_pk
                link = True
        if class_pk is not None and 'school_class_id' in defaults and not SchoolClass.objects.filter(
                pk=class_pk, school_id=plan.school_id).exists():
            raise ImportSchoolConflict()   # a planned link into a class of ANOTHER school would move the student: refuse
        try:
            student, created = import_store.write_row(plan.school_id, row.national_id, defaults)
        except import_store.ImportConflict:
            raise ImportSchoolConflict() from None   # lost a race / the id belongs to another school: generic refusal
        if student.school_id != plan.school_id:
            raise ImportSchoolConflict()   # belt and braces, inside the row's transaction: the row is rolled back
        ensure_current_enrollment(student, source='import')
        return student, created, link


class TierAwareSearchFilter(filters.SearchFilter):
    """``?search=``: names for every role; ``national_id`` only on full-tier rows (access.search_students)."""

    def filter_queryset(self, request, queryset, view):
        return search_students(queryset, request.query_params.get(self.search_param, ''))


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]  # پیش‌فرض
    filter_backends = [DjangoFilterBackend, TierAwareSearchFilter, filters.OrderingFilter]
    filterset_fields = ['grade', 'first_name', 'last_name', 'class_name']
    ordering_fields = ['first_name', 'last_name', 'grade', 'created_at']
    ordering = ['first_name']

    def destroy(self, request, *args, **kwargs):
        # Students with alerts, plans or risk events are archived, never deleted (change 0022: those rows PROTECT the student).
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({'detail': 'This student has linked records and cannot be deleted; deactivate instead.'},
                            status=status.HTTP_409_CONFLICT)

    def get_permissions(self):
        # همان قوانین قبلی
        if self.action == 'import_students':
            return [IsAdminUser()]  # فقط ادمین اجازه‌ی آپلود دارد
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        # Deny by default; the union of the user's grants (see students/access.py)
        return visible_students(self.request.user)

    # Reads are audit-logged like the pages (C-L): counts per school for the list, the object for one record.
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        audit.record_list(request.user, 'api_students', self.filter_queryset(self.get_queryset()))
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        audit.record(request.user, audit.VIEW_DETAIL, instance, detail='api')
        if getattr(instance, 'full_tier', False):
            audit.record(request.user, audit.NATIONAL_ID_REVEAL, instance, detail='api')   # the full id leaves only on a detail read
        return Response(self.get_serializer(instance).data)

    # Writes are SchoolAdmin only; the instance has no tier annotation, so mark it full for the response.
    def perform_create(self, serializer):
        serializer.save()
        ensure_current_enrollment(serializer.instance, source='manual')
        serializer.instance.full_tier = True

    def perform_update(self, serializer):
        serializer.save()
        ensure_current_enrollment(serializer.instance, source='manual')
        serializer.instance.full_tier = True

    # ✅ اکشن جدید برای آپلود فایل
    @action(detail=False, methods=['post'], url_path='import')
    def import_students(self, request):
        serializer = FileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # S2b: the school of the whole import is decided BEFORE the file is read, by the single rule (membership,
        # explicit target for several memberships / a superuser). It is never taken from the file.
        try:
            import_school_id = resolve_student_school(
                request.user, target_school_id=serializer.validated_data.get('target_school'))
        except StudentSchoolError as exc:
            return Response({'target_school': [exc.message]}, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        file_extension = file.name.split('.')[-1].lower()

        # Format first: a file we cannot parse is refused before a single byte is read.
        if file_extension not in ('csv', 'xlsx', 'xls'):
            return Response(
                {'error': 'فرمت فایل پشتیبانی نمی‌شود. فقط csv, xlsx, xls مجاز است.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # H-1: the size ceiling is enforced HERE, on the bytes, before pandas sees anything.
        payload = _bounded_upload(file)
        if payload is None:
            return Response({'error': IMPORT_TOO_LARGE}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # خواندن فایل بر اساس پسوند
            if file_extension == 'csv':
                # برای CSV باید encoding را utf-8-sig در نظر بگیریم تا فارسی به درستی خوانده شود
                df = pd.read_csv(TextIOWrapper(BytesIO(payload), encoding='utf-8-sig'), converters=TEXT_COLUMNS)
            else:
                df = pd.read_excel(BytesIO(payload), converters=TEXT_COLUMNS)

            # حذف رکوردهای خالی (NaN) برای جلوگیری از خطا
            df = df.dropna(how='all')
            
            if df.empty:
                return Response(
                    {'error': 'فایل خالی است یا داده‌ای در آن وجود ندارد.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # استانداردسازی نام ستون‌ها (حذف فاصله‌های اضافی و تبدیل به حروف کوچک)
            df.columns = df.columns.str.strip().str.lower()
            
            # مپ کردن ستون‌های احتمالی به نام فیلدهای مدل
            # کاربر می‌تواند ستون‌هایی با نام 'نام', 'نام خانوادگی', 'کد ملی' و ... داشته باشد
            column_mapping = {
                'نام': 'first_name',
                'نام خانوادگی': 'last_name',
                'نام خانوادگى': 'last_name',  # احتمال اشتباه تایپی
                'کد ملی': 'national_id',
                'کدملی': 'national_id',
                'پایه': 'grade',
                'پایه تحصیلی': 'grade',
                'کلاس': 'class_name',
                'شماره تماس': 'phone_number',
                'تلفن': 'phone_number',
                'موبایل': 'phone_number',
                'شغل پدر': 'father_job',
                'شغل مادر': 'mother_job',
            }
            
            # تغییر نام ستون‌ها در دیتافریم
            df = df.rename(columns=column_mapping)
            
            # لیست ستون‌های اجباری که حتماً باید در فایل باشند
            required_columns = ['first_name', 'last_name', 'national_id', 'grade']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return Response(
                    {'error': f'ستون‌های اجباری ({", ".join(missing_columns)}) در فایل وجود ندارند.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Pass 1: parse and validate every row; nothing is written yet.
            created_count = 0
            updated_count = 0
            row_errors = []   # (row index, message); restored to file order below
            parsed = []

            for index, row in df.iterrows():
                try:
                    # بررسی وجود کد ملی
                    national_id, national_id_error = _clean_national_id(row.get('national_id'))
                    if national_id_error:
                        row_errors.append((index, f"ردیف {index+2}: {national_id_error}"))
                        continue

                    # ساخت دیکشنری داده‌ها (class_name is not written by the import: school_class is the
                    # authoritative class relation and class_name is its derived mirror)
                    data = {
                        'first_name': str(row.get('first_name', '')).strip(),
                        'last_name': str(row.get('last_name', '')).strip(),
                        'national_id': national_id,
                        'phone_number': str(row.get('phone_number', '')).strip(),
                        'father_job': str(row.get('father_job', '')).strip(),
                        'mother_job': str(row.get('mother_job', '')).strip(),
                    }

                    # پردازش پایه (Grade)
                    grade_value = row.get('grade')
                    if pd.isna(grade_value):
                        row_errors.append((index, f"ردیف {index+2}: پایه تحصیلی خالی است."))
                        continue

                    try:
                        data['grade'] = int(float(grade_value))
                    except (ValueError, TypeError):
                        row_errors.append((index, f"ردیف {index+2}: مقدار پایه ({grade_value}) معتبر نیست."))
                        continue

                    # اعتبارسنجی پایه (بین ۷ تا ۱۲)
                    if data['grade'] not in [7, 8, 9, 10, 11, 12]:
                        row_errors.append((index, f"ردیف {index+2}: پایه باید بین ۷ تا ۱۲ باشد."))
                        continue

                    # the RAW class cell goes to the resolver (never str(): NaN and numbers need their type)
                    parsed.append(ImportRow(index, national_id, data, row.get('class_name')))

                except Exception as e:
                    row_errors.append((index, f"ردیف {index+2}: خطا - {str(e)}"))

            # Each row has its own transaction: a failing row never rolls back the others.
            linked_ids = set()

            def write(item, plan):
                nonlocal created_count, updated_count
                try:
                    student, created, linked_now = _write_import_row(item, plan)
                    if linked_now:
                        linked_ids.add(student.pk)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except ImportSchoolConflict as e:
                    row_errors.append((item.index, f"ردیف {item.index+2}: {e}"))
                except Exception as e:
                    row_errors.append((item.index, f"ردیف {item.index+2}: خطا - {str(e)}"))

            # Pass 2a: students that ALREADY have a class are written first. Their rows never change a link,
            # but may change a grade, and class decisions must see the grades that were really stored.
            already_linked = _linked_national_ids(parsed, import_school_id)
            no_links = ClassLinkPlan(import_school_id)
            for item in parsed:
                if item.national_id in already_linked:
                    write(item, no_links)

            # Pass 2b: class decisions for the whole file, on persisted state, before any new link is written.
            plan = _plan_class_links(parsed, import_school_id)

            # Pass 3: write the remaining rows (new students and students without a class), in file order.
            for item in parsed:
                if item.national_id not in already_linked:
                    write(item, plan)

            errors = [message for _index, message in sorted(row_errors, key=lambda pair: pair[0])]
            return Response({
                'status': 'success',
                'created': created_count,
                'updated': updated_count,
                'errors': errors,
                'total_rows': len(df),
                'linked': len(linked_ids),
                'preserved_links': plan.preserved_links,
                'class_blank': plan.class_blank,
                'unmatched_classes': plan.unmatched[:UNMATCHED_LIST_LIMIT],
                'unmatched_classes_truncated': len(plan.unmatched) > UNMATCHED_LIST_LIMIT,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'خطا در پردازش فایل: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    @action(detail=True, methods=['get'], url_path='features')
    def get_features(self, request, pk=None):
        student = self.get_object()
        grades = visible_grades(request.user).filter(student=student)
        avg_score = grades.aggregate(Avg('score'))['score__avg'] or 0
        attendances = visible_attendances(request.user).filter(student=student)
        total_absences = attendances.filter(status='absent').count()
        total_lates = attendances.filter(status='late').count()
        total_days = attendances.count()
        attendance_rate = 1 - (total_absences / (total_days + 1))
        
        data = {
            "grade": student.grade,
            "attendance_rate": round(attendance_rate, 2),
            "avg_completion_rate": 0.8,  # از مدل Homework محاسبه شود
            "avg_exam_score": round(avg_score, 2),
            "total_absences": total_absences,
            "total_lates": total_lates,
            "total_communications": 3,  # از مدل Communication محاسبه شود
            "completed_homework": 12    # از مدل Homework محاسبه شود
        }
        return Response(data)

    @action(detail=True, methods=['get'], url_path='predict')
    def predict_status(self, request, pk=None):
        student = self.get_object()

        grades = visible_grades(request.user).filter(student=student)
        attendances = visible_attendances(request.user).filter(student=student)
        avg_score = grades.aggregate(Avg('score'))['score__avg'] or 0
        total_absences = attendances.filter(status='absent').count()
        total_lates = attendances.filter(status='late').count()
        attendance_rate = 1 - (total_absences / (attendances.count() + 1))  # +1 avoids division by zero

        # Placeholder constants kept as-is (Stage 0 A-02): not real homework/communication data.
        input_data = {
            "grade": student.grade,
            "attendance_rate": round(attendance_rate, 2),
            "avg_completion_rate": 0.8,
            "avg_exam_score": round(avg_score, 2),
            "total_absences": total_absences,
            "total_lates": total_lates,
            "total_communications": 3,
            "completed_homework": 12,
        }

        try:
            fastapi_url = "http://fastapi:8001/predict/"
            response = requests.post(
                fastapi_url, json=input_data, headers=service_headers(request.user), timeout=5
            )
            response.raise_for_status()
            result = response.json()

            return Response({
                "student": f"{student.first_name} {student.last_name}",
                "input_data": input_data,
                "prediction_result": result
            })

        except (requests.exceptions.RequestException, ImproperlyConfigured) as e:
            return Response(
                {"error": "خطا در ارتباط با سرویس AI"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
