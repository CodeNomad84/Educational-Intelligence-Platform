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
import { COMPETENCY_AXES, GRADES, RADAR_BY_GRADE, RADAR_TARGET, type Grade } from "@/data/school";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";

const fa = (n: number) => n.toLocaleString("fa-IR");

type Scope = "all" | Grade;

export function CompetencyRadar() {
  const { openChat, setMascotHold, flashMascot } = useDashboard();
  const [scope, setScope] = useState<Scope>("all");
  const values = RADAR_BY_GRADE[scope];

  const data = COMPETENCY_AXES.map((a) => ({
    axis: a.label,
    current: values[a.key],
    target: RADAR_TARGET[a.key],
  }));
  const { weakest, strongest } = useMemo(() => {
    const sorted = [...data].sort((a, b) => a.current - b.current);
    return { weakest: sorted[0], strongest: sorted[sorted.length - 1] };
  }, [data]);

  const scopeLabel = scope === "all" ? "کل مدرسه" : `پایه ${scope}`;

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
            رادار شایستگی‌های شش‌گانه
          </h2>
          <p className="text-sm text-muted-foreground">
            میانگین شش محور تربیتی در برابر هدف مأموریت
          </p>
        </div>
        <div
          role="tablist"
          aria-label="انتخاب پایه"
          className="flex flex-wrap gap-1 rounded-full border border-border bg-surface/60 p-1"
        >
          {(["all", ...GRADES] as Scope[]).map((g) => (
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
              {g === "all" ? "همه" : g}
            </button>
          ))}
        </div>
      </div>

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
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Radar
              name="هدف مأموریت"
              dataKey="target"
              stroke="var(--success)"
              strokeDasharray="5 4"
              strokeWidth={2}
              fill="var(--success)"
              fillOpacity={0.06}
            />
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
              formatter={(v: number, name: string) => [fa(v), name]}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-5 rounded-full bg-gradient-primary" />
          {scopeLabel}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-0 w-5 border-t-2 border-dashed border-success" />
          هدف مأموریت
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-success/25 bg-success/10 p-3">
          <p className="flex items-center gap-1.5 text-xs text-success">
            <TrendingUp className="size-3.5" />
            قوی‌ترین محور
          </p>
          <p className="mt-1 font-bold">
            {strongest?.axis} · {fa(strongest?.current ?? 0)}
          </p>
        </div>
        <div className="rounded-2xl border border-warning/25 bg-warning/10 p-3">
          <p className="flex items-center gap-1.5 text-xs text-warning">
            <Target className="size-3.5" />
            فرصت رشد
          </p>
          <p className="mt-1 font-bold">
            {weakest?.axis} · {fa(weakest?.current ?? 0)}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              (فاصله تا هدف {fa((weakest?.target ?? 0) - (weakest?.current ?? 0))})
            </span>
          </p>
        </div>
      </div>

      <Button
        variant="soft"
        size="pill"
        className="mt-4 w-full"
        onClick={() => {
          flashMascot("analytical");
          openChat(
            `رادار شایستگی ${scopeLabel} را تحلیل کن. محور «${weakest?.axis}» با ${weakest?.current} کمترین امتیاز را دارد. چه مأموریت‌ها و اقداماتی برای رسیدن به هدف پیشنهاد می‌کنی؟`,
          );
        }}
      >
        <ScanSearch /> تحلیل عمیق با رهنما
      </Button>
    </section>
  );
}
