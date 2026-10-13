# DEMO SCOPE — whole file. Views for the demo dashboards. Only reachable when settings.DEMO_MODE is true.
# Authorization: every view is Admin-role only (same policy as the existing school-wide dashboard, S-04).
from django.shortcuts import render
from django.utils import timezone

from dashboard.decorators import role_required
from students.access import ADMIN
from students.models import Student

from . import assistant as assistant_mod
from .analytics import school_overview, sort_by_attention, student_trends
from .engine import analyze_students
from .models import CounselingNote, InterventionRecord, StudentObservation


def _all():
    today = timezone.localdate()
    students = list(Student.objects.all())
    return today, students, analyze_students(students, today)


def school_dashboard(request):
    """Called from dashboard.views.dashboard_view (DEMO SCOPE hook); caller has verified the Admin role."""
    today, students, results = _all()
    overview = school_overview(students, results, today)
    top = [{"student": s, "r": results[s.id]} for s in overview["attention"][:8]]
    return render(request, "demo_intel/school_dashboard.html", {"o": overview, "top": top, "active": "dashboard"})


@role_required(ADMIN)
def counselor_view(request):
    today, students, results = _all()
    cases = []
    for s in sort_by_attention(students, results):
        r = results[s.id]
        if r["level"] == "LOW":
            continue
        cases.append({
            "student": s, "r": r,
            "interventions": list(InterventionRecord.objects.filter(student=s)[:3]),
            "last_counseling": CounselingNote.objects.filter(student=s).values_list("date", flat=True).first(),
        })
    return render(request, "demo_intel/counselor.html", {"cases": cases, "active": "counselor"})


@role_required(ADMIN)
def demo_student_list(request):
    today, students, results = _all()
    level = request.GET.get("level", "")
    cls = request.GET.get("class", "")
    q = request.GET.get("q", "").strip()
    rows = []
    for s in sort_by_attention(students, results):
        r = results[s.id]
        if level and r["level"] != level:
            continue
        if cls and s.class_name != cls:
            continue
        if q and q not in f"{s.first_name} {s.last_name}":
            continue
        rows.append({"student": s, "r": r})
    classes = sorted({s.class_name for s in students})
    return render(request, "demo_intel/student_list.html",
                  {"rows": rows, "classes": classes, "level": level, "cls": cls, "q": q, "active": "students"})


def student_profile(request, student):
    """Called from dashboard.views.student_detail_view (DEMO SCOPE hook); caller has verified the Admin role."""
    today = timezone.localdate()
    result = analyze_students([student], today)[student.id]
    ctx = {
        "student": student, "r": result, "trends": student_trends(student, today), "active": "students",
        "grades": student.grades.all()[:18],
        "attendance_counts": {
            "absent": student.attendances.filter(status="absent").count(),
            "late": student.attendances.filter(status="late").count(),
            "total": student.attendances.count(),
        },
        "observations": StudentObservation.objects.filter(student=student)[:8],
        "interventions": InterventionRecord.objects.filter(student=student),
        "counseling": CounselingNote.objects.filter(student=student)[:4],
    }
    return render(request, "demo_intel/student_profile.html", ctx)


@role_required(ADMIN)
def assistant_view(request):
    query = request.POST.get("query", "").strip() if request.method == "POST" else request.GET.get("q", "").strip()
    result = assistant_mod.answer(query) if query else None
    return render(request, "demo_intel/assistant.html", {
        "result": result, "query": query, "suggestions": assistant_mod.SUGGESTIONS, "active": "assistant"})
