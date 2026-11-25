import { motion } from "framer-motion";
import { Activity, ClipboardCheck, GraduationCap, TriangleAlert, Users } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

import { faNum, type Kpi } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";

const ORDER = ["students", "average", "attendance", "observations"] as const;

const ICONS: Record<string, typeof Users> = {
  students: Users,
  average: GraduationCap,
  attendance: Activity,
  observations: ClipboardCheck,
  alerts_open: TriangleAlert,
};

const TONE: Record<Kpi["tone"], { icon: string; stroke: string }> = {
  primary: { icon: "bg-primary/15 text-primary-glow", stroke: "var(--primary-glow)" },
  info: { icon: "bg-info/15 text-info", stroke: "var(--info)" },
  success: { icon: "bg-success/15 text-success", stroke: "var(--success)" },
  warning: { icon: "bg-warning/15 text-warning", stroke: "var(--warning)" },
  danger: { icon: "bg-destructive/15 text-destructive", stroke: "var(--destructive)" },
};

export function KpiStrip() {
  const { summary, loading } = useDashboard();
  const kpis = (summary?.kpis ?? []).filter((k) => (ORDER as readonly string[]).includes(k.key));

  return (
    <section
      id="pulse"
      aria-label="نبض مدرسه"
      className="grid scroll-mt-24 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      {ORDER.map((key, i) => {
        const k = kpis.find((x) => x.key === key);
        if (!k) {
          return (
            <div key={key} className="rounded-3xl glass p-5 text-sm text-muted-foreground">
              {loading ? "در حال دریافت…" : "داده‌ای ثبت نشده"}
            </div>
          );
        }
        const Icon = ICONS[k.key] ?? Activity;
        const tone = TONE[k.tone];
        const series = (k.series ?? []).filter((v): v is number => typeof v === "number");
        const data = series.map((v, idx) => ({ idx, v }));
        return (
          <motion.article
            key={k.key}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.06 }}
            whileHover={{ y: -3 }}
            className="group relative overflow-hidden rounded-3xl glass p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <span className={cn("grid size-11 place-items-center rounded-2xl", tone.icon)}>
                <Icon className="size-5" aria-hidden />
              </span>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">{k.label}</p>
            <div className="mt-1 flex items-end justify-between gap-2">
              <p className="text-3xl font-black tracking-tight">
                {k.value === null ? "—" : faNum(k.value)}
              </p>
              {k.unit && <p className="pb-1 text-xs text-muted-foreground">{k.unit}</p>}
            </div>
            <div className="-mx-5 -mb-5 mt-3 h-14" aria-hidden>
              {data.length > 1 && (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id={`spark-${k.key}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={tone.stroke} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={tone.stroke} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="v"
                      stroke={tone.stroke}
                      strokeWidth={2}
                      fill={`url(#spark-${k.key})`}
                      isAnimationActive
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </motion.article>
        );
      })}
    </section>
  );
}
