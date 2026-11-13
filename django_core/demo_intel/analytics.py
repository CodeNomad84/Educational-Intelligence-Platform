# DEMO SCOPE — whole file. Aggregations for the demo dashboards (read-only).
from collections import defaultdict
from datetime import timedelta

from students.models import Attendance, Grade

from .fa import digits

LEVEL_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def sort_by_attention(students, results):
    return sorted(students, key=lambda s: (LEVEL_ORDER[results[s.id]["level"]], -results[s.id]["score"], s.last_name))


def _weekly_absence(att_rows, today, weeks=12):
    buckets = defaultdict(lambda: [0, 0])  # week index -> [absent, total]
    for d, status in att_rows:
        w = (today - d).days // 7
        if 0 <= w < weeks:
            buckets[w][1] += 1
            buckets[w][0] += status == "absent"
    labels, values = [], []
    for w in range(weeks - 1, -1, -1):
        absent, total = buckets[w]
        labels.append(digits(f"{w + 1} هفته قبل") if w else "هفتهٔ جاری")
        values.append(round(absent / total * 100, 1) if total else None)
    return labels, values


def _score_buckets(grade_rows, today, days=120, step=15):
    buckets = defaultdict(list)
    for d, score in grade_rows:
        b = (today - d).days // step
        if 0 <= b < days // step:
            buckets[b].append(score)
    labels, values = [], []
    for b in range(days // step - 1, -1, -1):
        labels.append(digits(f"{(b + 1) * step}–{b * step} روز قبل"))
        values.append(round(sum(buckets[b]) / len(buckets[b]), 2) if buckets[b] else None)
    return labels, values


def school_overview(students, results, today):
    ids = [s.id for s in students]
    dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for s in students:
        dist[results[s.id]["level"]] += 1

    att_rows = list(Attendance.objects.filter(student_id__in=ids, date__gte=today - timedelta(days=84))
                    .values_list("date", "status"))
    grade_rows = list(Grade.objects.filter(student_id__in=ids, date__gte=today - timedelta(days=120))
                      .values_list("date", "score"))
    att_labels, att_values = _weekly_absence(att_rows, today)
    sc_labels, sc_values = _score_buckets(grade_rows, today)

    classes = defaultdict(list)
    for s in students:
        classes[s.class_name].append(s)
    class_rows = []
    for name, members in sorted(classes.items()):
        ab = [results[s.id]["metrics"]["absence_recent"] for s in members if results[s.id]["metrics"]["absence_recent"] is not None]
        av = [results[s.id]["metrics"]["avg_recent"] for s in members if results[s.id]["metrics"]["avg_recent"] is not None]
        class_rows.append({
            "name": name, "count": len(members),
            "absence": round(sum(ab) / len(ab), 1) if ab else None,
            "average": round(sum(av) / len(av), 1) if av else None,
            "high": sum(results[s.id]["level"] == "HIGH" for s in members),
            "medium": sum(results[s.id]["level"] == "MEDIUM" for s in members),
        })

    recent_abs = [r["metrics"]["absence_recent"] for r in results.values() if r["metrics"]["absence_recent"] is not None]
    recent_avg = [r["metrics"]["avg_recent"] for r in results.values() if r["metrics"]["avg_recent"] is not None]
    return {
        "total": len(students),
        "distribution": dist,
        "avg_absence": round(sum(recent_abs) / len(recent_abs), 1) if recent_abs else None,
        "avg_score": round(sum(recent_avg) / len(recent_avg), 1) if recent_avg else None,
        "attendance_trend": {"labels": att_labels, "values": att_values},
        "academic_trend": {"labels": sc_labels, "values": sc_values},
        "classes": class_rows,
        "attention": [s for s in sort_by_attention(students, results) if results[s.id]["level"] != "LOW"],
    }


def student_trends(student, today):
    att = list(Attendance.objects.filter(student=student, date__gte=today - timedelta(days=84))
               .values_list("date", "status"))
    grades = list(Grade.objects.filter(student=student, date__gte=today - timedelta(days=120))
                  .values_list("date", "score"))
    a_l, a_v = _weekly_absence(att, today)
    s_l, s_v = _score_buckets(grades, today)
    return {"attendance": {"labels": a_l, "values": a_v}, "scores": {"labels": s_l, "values": s_v}}
