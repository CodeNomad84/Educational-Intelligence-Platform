/**
 * Types and fetch helper for the real Django dashboard summary (Phase 3, Step 1).
 * `GET /api/dashboard/` is the aggregate endpoint in `django_core/dashboard/summary_api.py`.
 */
import { apiFetch } from "./api";

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

export interface StudentRow {
  id: number;
  name: string;
  grade: number;
  classroom: string;
  gpa: number | null;
  attendance_rate: number | null;
  status: "excellent" | "growing" | "attention" | "risk";
  observations: unknown[];
}

export interface AlertItem {
  id: number;
  student_name: string;
  grade: number;
  severity_label: string;
  type_label: string;
  message: string;
  text_hidden: boolean;
}

export interface DashboardSummary {
  meta: { academic_year: string | null; generated_at: string; min_group: number };
  kpis: Kpi[];
  attendance_trend: TrendPoint[];
  average_trend: TrendPoint[];
  subjects: SubjectAverage[];
  subjects_by_grade: { grade: number; subjects: SubjectAverage[] }[];
  grades_present: number[];
  alerts: AlertItem[];
  students: StudentRow[];
}

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function faNum(n: number): string {
  return String(n).replace(/\d/g, (d) => PERSIAN_DIGITS[Number(d)] ?? d);
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard/");
}
