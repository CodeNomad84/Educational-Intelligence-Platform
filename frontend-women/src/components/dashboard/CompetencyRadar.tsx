import { ScanSearch, Target, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { Button } from "@/components/ui/button";
import { faNum, type SubjectAverage } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";

export function CompetencyRadar() {
  const { summary, openChat, setMascotHold, flashMascot } = useDashboard();
  const [scope, setScope] = useState<string>("all");

  const grades = summary?.grades_present ?? [];
  const subjects: SubjectAverage[] = useMemo(() => {
    if (!summary) return [];
    if (scope === "all") return summary.subjects;
    const row = summary.subjects_by_grade.find((r) => String(r.grade) === scope);
    return row?.subjects ?? [];
  }, [summary, scope]);

  const data = subjects.map((s) => ({ axis: s.label, current: s.average }));
  const { strongest, weakest } = useMemo(() => {
    if (data.length === 0) return { strongest: null, weakest: null };
    const sorted = [...data].sort((a, b) => a.current - b.current);
    return { strongest: sorted[sorted.length - 1] ?? null, weakest: sorted[0] ?? null };
  }, [data]);

  const scopeLabel = scope === "all" ? "کل مدرسه" : `پایه ${faNum(Number(scope))}`;
  const scopes = ["all", ...grades.map(String)];

  return (
    <section
      id="radar"
      aria-labelledby="radar-title"
      className="scroll-mt-24 rounded-3xl glass p-5 sm:p-6"
      onMouseEnter={() => setMascotHold("analytical")}
      onMouseLeave={() => setMascotHold(null)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="radar-title" className="text-lg font-extrabold">
            عملکرد دروس
          </h2>
          <p className="text-sm text-muted-foreground">میانگین نمرات هر درس (از ۲۰)</p>
        </div>
        <div
          role="tablist"
          aria-label="انتخاب پایه"
          className="flex flex-wrap gap-1 rounded-full border border-border bg-surface/60 p-1"
        >
          {scopes.map((g) => (
            <button
              key={g}
              role="tab"
              aria-selected={scope === g}
              onClick={() => setScope(g)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                scope === g
                  ? "bg-gradient-primary text-primary-foreground shadow-glow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {g === "all" ? "همه" : faNum(Number(g))}
            </button>
          ))}
        </div>
      </div>

      {data.length === 0 ? (
        <div className="mt-2 grid h-[300px] place-items-center text-sm text-muted-foreground">
          هنوز نمره‌ای برای این بازه ثبت نشده است.
        </div>
      ) : (
        <div className="mt-2 h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="72%">
              <defs>
                <linearGradient id="radar-fill" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.6} />
                  <stop offset="100%" stopColor="var(--primary-glow)" stopOpacity={0.35} />
                </linearGradient>
              </defs>
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{
                  fill: "var(--foreground)",
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: "inherit",
                }}
              />
              <PolarRadiusAxis domain={[0, 20]} tick={false} axisLine={false} />
              <Radar
                name={scopeLabel}
                dataKey="current"
                stroke="var(--primary-glow)"
                strokeWidth={2.5}
                fill="url(#radar-fill)"
                dot={{ r: 3.5, fill: "var(--primary-glow)" }}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--popover)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  direction: "rtl",
                  fontFamily: "inherit",
                }}
                labelStyle={{ color: "var(--foreground)", fontWeight: 700 }}
                itemStyle={{ color: "var(--muted-foreground)" }}
                formatter={(v: number, name: string) => [faNum(v), name]}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.length > 0 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-success/25 bg-success/10 p-3">
            <p className="flex items-center gap-1.5 text-xs text-success">
              <TrendingUp className="size-3.5" />
              قوی‌ترین درس
            </p>
            <p className="mt-1 font-bold">
              {strongest?.axis} · {strongest ? faNum(strongest.current) : "—"}
            </p>
          </div>
          <div className="rounded-2xl border border-warning/25 bg-warning/10 p-3">
            <p className="flex items-center gap-1.5 text-xs text-warning">
              <Target className="size-3.5" />
              نیازمند توجه
            </p>
            <p className="mt-1 font-bold">
              {weakest?.axis} · {weakest ? faNum(weakest.current) : "—"}
            </p>
          </div>
        </div>
      )}

      <Button
        variant="soft"
        size="pill"
        className="mt-4 w-full"
        onClick={() => {
          flashMascot("analytical");
          openChat(
            `عملکرد دروس ${scopeLabel} را تحلیل کن. قوی‌ترین درس «${strongest?.axis ?? "—"}» و ضعیف‌ترین «${weakest?.axis ?? "—"}» است. چه اقداماتی پیشنهاد می‌کنی؟`,
          );
        }}
      >
        <ScanSearch /> تحلیل عمیق با رهنما
      </Button>
    </section>
  );
}
