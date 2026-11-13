import { motion } from "framer-motion";
import { Activity, ClipboardCheck, Rocket, TrendingDown, TrendingUp, Users } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

import { KPIS, type KpiMetric } from "@/data/school";
import { cn } from "@/lib/utils";

const ICONS = { mentees: Users, projects: Rocket, growth: Activity, observations: ClipboardCheck } as const;

const TONE: Record<KpiMetric["tone"], { icon: string; stroke: string }> = {
  primary: { icon: "bg-primary/15 text-primary-glow", stroke: "var(--primary-glow)" },
  info: { icon: "bg-info/15 text-info", stroke: "var(--info)" },
  success: { icon: "bg-success/15 text-success", stroke: "var(--success)" },
  warning: { icon: "bg-warning/15 text-warning", stroke: "var(--warning)" },
};

export function KpiStrip() {
  return (
    <section id="pulse" aria-label="نبض مدرسه" className="grid scroll-mt-24 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {KPIS.map((k, i) => {
        const Icon = ICONS[k.id as keyof typeof ICONS] ?? Activity;
        const tone = TONE[k.tone];
        const data = k.series.map((v, idx) => ({ idx, v }));
        return (
          <motion.article
            key={k.id}
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
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold",
                  k.trend === "up" ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive",
                )}
              >
                {k.trend === "up" ? <TrendingUp className="size-3.5" /> : <TrendingDown className="size-3.5" />}
                <span dir="ltr">{k.delta}</span>
              </span>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">{k.label}</p>
            <div className="mt-1 flex items-end justify-between gap-2">
              <p className="text-3xl font-black tracking-tight">{k.value}</p>
              <p className="pb-1 text-xs text-muted-foreground">{k.deltaLabel}</p>
            </div>
            <div className="-mx-5 -mb-5 mt-3 h-14" aria-hidden>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id={`spark-${k.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={tone.stroke} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={tone.stroke} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="v" stroke={tone.stroke} strokeWidth={2} fill={`url(#spark-${k.id})`} isAnimationActive />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.article>
        );
      })}
    </section>
  );
}
