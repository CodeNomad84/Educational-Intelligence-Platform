/**
 * Types and fetch helper for the real Django dashboard summary (Phase 3, Step 1).
 *
 * `GET /api/dashboard/` is the aggregate endpoint in `django_core/dashboard/summary_api.py`.
 * All figures come from the caller's own `visible_*` scopes, so every role sees its own data
 * (empty lists / null values when nothing is granted), never an unfiltered number.
 */
import { apiFetch } from "./api";

export type AcademicStatus = "excellent" | "growing" | "attention" | "risk";

export interface Kpi {
  key: string;
  label: string;
  value: number | null;
  unit: string | null;
  tone: "primary" | "info" | "success" | "warning" | "danger";
  series: (number | null)[] | null;
}

export interface TrendPoint {
  label: string;
  value: number | null;
}

export interface SubjectAverage {
  label: string;
  average: number;
}

export interface SubjectsByGrade {
  grade: number;
  subjects: SubjectAverage[];
}

export interface PersianDate {
  day: number;
  month: number;
}

export interface Observation {
  kind: "kudos" | "suggestion" | "alert";
  text: string;
  mentor: string;
  date: PersianDate | null;
}

export interface AlertItem {
  id: number;
  student_id: number;
  student_name: string;
  grade: number;
  type: string;
  type_label: string;
  severity: string;
  severity_label: string;
  status: string;
  created_at: PersianDate | null;
  message: string;
  text_hidden: boolean;
}

export interface StudentRow {
  id: number;
  name: string;
  grade: number;
  classroom: string;
  gpa: number | null;
  attendance_rate: number | null;
  status: AcademicStatus;
  observations: Observation[];
}

export interface DashboardSummary {
  meta: {
    academic_year: string | null;
    generated_at: string;
    min_group: number;
  };
  kpis: Kpi[];
  attendance_trend: TrendPoint[];
  average_trend: TrendPoint[];
  subjects: SubjectAverage[];
  subjects_by_grade: SubjectsByGrade[];
  grades_present: number[];
  alerts: AlertItem[];
  students: StudentRow[];
}

export const STATUS_META: Record<
  AcademicStatus,
  { label: string; tone: "success" | "info" | "warning" | "destructive" }
> = {
  excellent: { label: "درخشان", tone: "success" },
  growing: { label: "رو به رشد", tone: "info" },
  attention: { label: "نیازمند توجه", tone: "warning" },
  risk: { label: "نیازمند مداخله", tone: "destructive" },
};

const PERSIAN_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function faNum(n: number): string {
  return String(n).replace(/\d/g, (d) => PERSIAN_DIGITS[Number(d)] ?? d);
}

export function formatPersianDate(date: PersianDate | null): string {
  if (!date) return "—";
  return `${faNum(date.day)} ${PERSIAN_MONTHS[date.month - 1] ?? ""}`.trim();
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard/");
}

export type StreamKind = "milestone" | "kudos" | "alert";

export interface StreamItem {
  id: string;
  kind: StreamKind;
  title: string;
  body: string;
  studentId?: number;
  author: string;
  time: string;
  tag: string;
}

const OBS_LABEL: Record<Observation["kind"], string> = {
  kudos: "تشویق",
  suggestion: "پیشنهاد رشد",
  alert: "هشدار",
};

/** Turn the live summary (open alerts + the latest staff observations) into the growth board. */
export function buildStream(summary: DashboardSummary): StreamItem[] {
  const items: StreamItem[] = [];
  for (const alert of summary.alerts) {
    items.push({
      id: `alert-${alert.id}`,
      kind: "alert",
      title: `هشدار ${alert.severity_label} — ${alert.student_name}`,
      body: alert.text_hidden ? "متن این هشدار برای نقش شما قابل نمایش نیست." : alert.message,
      studentId: alert.student_id,
      author: alert.type_label,
      time: formatPersianDate(alert.created_at),
      tag: `پایه ${faNum(alert.grade)}`,
    });
  }
  for (const student of summary.students) {
    for (const obs of student.observations) {
      items.push({
        id: `obs-${student.id}-${items.length}`,
        kind: obs.kind === "kudos" ? "kudos" : obs.kind === "alert" ? "alert" : "milestone",
        title: `${student.name} — ${OBS_LABEL[obs.kind]}`,
        body: obs.text,
        studentId: student.id,
        author: obs.mentor,
        time: formatPersianDate(obs.date),
        tag: `پایه ${faNum(student.grade)}`,
      });
    }
  }
  return items;
}
