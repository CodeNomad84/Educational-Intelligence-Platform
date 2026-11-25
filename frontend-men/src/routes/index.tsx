import { createFileRoute } from "@tanstack/react-router";
import {
  Sparkles,
  Send,
  Users,
  ShieldCheck,
  FileText,
  Trophy,
  Zap,
  TrendingUp,
  AlertTriangle,
} from "lucide-react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { useEffect, useState } from "react";
import { MascotAssistant, type MascotMood } from "@/components/MascotAssistant";
import { ApiError } from "@/lib/api";
import { faNum, fetchDashboardSummary, type DashboardSummary } from "@/lib/dashboard";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "سکوی آموزشی-تربیتی آرمان نو | سامانه هوشمند رشد" },
      {
        name: "description",
        content: "داشبورد هوشمند پایش رشد دانش‌آموزان و کادر آموزشی مدارس پسرانه",
      },
      { property: "og:title", content: "سکوی آموزشی-تربیتی آرمان نو" },
      { property: "og:description", content: "داشبورد هوشمند پایش رشد دانش‌آموزان مدارس پسرانه" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const tip = {
  contentStyle: {
    background: "var(--background)",
    border: "1px solid var(--border)",
    borderRadius: 12,
  },
};

function useDashboardSummary() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDashboardSummary()
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401 && typeof window !== "undefined") {
          window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
          return;
        }
        setError(err instanceof Error ? err.message : "خطا در دریافت داده‌ها");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { summary, loading, error };
}

function Index() {
  const { summary, loading, error } = useDashboardSummary();
  const [mood, setMood] = useState<MascotMood>("idle");
  const [q, setQ] = useState("");

  const kpis = summary?.kpis ?? [];
  const kpi = (key: string) => kpis.find((x) => x.key === key);
  const students = summary?.students ?? [];
  const alerts = summary?.alerts ?? [];
  const interventions = (kpi("alerts_open")?.value ?? 0) + (kpi("plans_open")?.value ?? 0);

  const cards = [
    { t: "دانش‌آموزان فعال", v: kpi("students")?.value ?? null, d: null, I: Users },
    { t: "میانگین نمرات", v: kpi("average")?.value ?? null, d: "از ۲۰", I: TrendingUp },
    { t: "نرخ حضور", v: kpi("attendance")?.value ?? null, d: "٪", I: ShieldCheck },
    { t: "مداخلات و هشدارها", v: interventions, d: "باز", I: FileText },
  ];

  const radar = (summary?.subjects ?? []).map((s) => ({ k: s.label, v: s.average }));
  const line = (summary?.average_trend ?? []).map((t) => ({ m: t.label, a: t.value }));
  const top = [...students]
    .filter((s) => s.gpa !== null)
    .sort((a, b) => (b.gpa ?? 0) - (a.gpa ?? 0))
    .slice(0, 5);

  const excellent = students.filter((s) => s.status === "excellent").length;
  const attention = students.filter((s) => s.status === "attention" || s.status === "risk").length;
  const badges = [
    { t: "دانش‌آموزان ممتاز", d: `${faNum(excellent)} دانش‌آموز این ماه`, I: Zap },
    { t: "نیازمند توجه", d: `${faNum(attention)} دانش‌آموز در پایش اخیر`, I: TrendingUp },
    { t: "هشدارهای باز", d: `${faNum(alerts.length)} هشدار در انتظار بررسی`, I: AlertTriangle },
  ];

  const run = () => {
    setMood("thinking");
    setTimeout(() => {
      setMood("insight");
      setTimeout(() => setMood("idle"), 4000);
    }, 2800);
  };
  const ask = () => {
    if (!q.trim()) return;
    run();
  };

  return (
    <div className="min-h-screen grid-bg">
      <div className="hero-bg min-h-screen">
        <main className="mx-auto max-w-7xl space-y-6 px-4 py-8">
          <header className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-extrabold md:text-2xl">
                سکوی آموزشی-تربیتی <span className="text-primary">آرمان نو</span>
              </h1>
              <p className="text-sm text-muted-foreground">
                سامانه هوشمند رشد، مربیگری و انتخاب مأموریت‌محور
              </p>
            </div>
            <span className="rounded-full border border-gold/40 bg-gold/10 px-3 py-1 text-xs font-bold text-gold">
              {summary?.meta.academic_year ? `سال تحصیلی ${summary.meta.academic_year}` : "—"}
            </span>
          </header>

          {(loading || error) && (
            <p className="rounded-2xl border border-border bg-card px-4 py-3 text-center text-sm text-muted-foreground">
              {loading
                ? "در حال دریافت داده‌های زنده از سامانه…"
                : `دریافت داده‌ها ممکن نشد: ${error}`}
            </p>
          )}

          <section className="glass relative overflow-hidden p-6 md:p-10">
            <div className="grid items-center gap-6 md:grid-cols-[1fr_260px]">
              <div className="space-y-5">
                <div className="flex items-center gap-2 text-sm text-gold">
                  <Sparkles className="size-4" /> مرکز فرماندهی هوشمند
                </div>
                <h2 className="text-2xl font-extrabold md:text-4xl">
                  سلام! امروز روی رشد کدام <span className="text-primary">مأموریت</span> کار کنیم؟
                </h2>
                <div className="glow-primary ai-focus flex items-center gap-2 rounded-2xl border border-primary/40 bg-background/70 p-2">
                  <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onFocus={() => setMood((m) => (m === "idle" ? "insight" : m))}
                    onBlur={() => setMood((m) => (m === "insight" ? "idle" : m))}
                    onKeyDown={(e) => e.key === "Enter" && ask()}
                    className="flex-1 bg-transparent px-3 py-3 outline-none placeholder:text-muted-foreground"
                    placeholder="از دستیار هوشمند رشد و مربیگری بپرسید..."
                  />
                  <button
                    onClick={ask}
                    aria-label="ارسال"
                    className="rounded-xl bg-primary p-3 text-primary-foreground transition hover:scale-105"
                  >
                    <Send className="size-5 -scale-x-100" />
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {["تحلیل شاخص مأموریت‌محور", "ارزیابی رشد دانش‌آموزان", "ثبت مشاهده تربیتی"].map(
                    (c) => (
                      <button
                        key={c}
                        onClick={() => {
                          setQ(c);
                          run();
                        }}
                        className="rounded-full border border-border bg-accent/60 px-4 py-2 text-sm transition hover:border-primary hover:text-primary"
                      >
                        {c}
                      </button>
                    ),
                  )}
                </div>
              </div>
              <MascotAssistant mood={mood} />
            </div>
          </section>

          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {cards.map(({ t, v, d, I }) => (
              <div key={t} className="glass p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t}</span>
                  <span className="rounded-lg bg-indigo-deep p-2 text-primary">
                    <I className="size-5" />
                  </span>
                </div>
                <div className="mt-3 text-3xl font-extrabold">{v === null ? "—" : faNum(v)}</div>
                <div className="mt-1 flex items-end justify-between gap-2">
                  <span className="text-xs text-gold">{d ?? ""}</span>
                </div>
              </div>
            ))}
          </section>

          <section className="grid gap-4 lg:grid-cols-3">
            <div className="glass p-5">
              <h3 className="mb-2 font-bold">عملکرد دروس</h3>
              <div className="h-72">
                {radar.length === 0 ? (
                  <div className="grid h-full place-items-center text-sm text-muted-foreground">
                    هنوز نمره‌ای ثبت نشده است.
                  </div>
                ) : (
                  <ResponsiveContainer>
                    <RadarChart data={radar} outerRadius="70%">
                      <PolarGrid stroke="var(--border)" />
                      <PolarAngleAxis
                        dataKey="k"
                        tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                      />
                      <PolarRadiusAxis domain={[0, 20]} tick={false} axisLine={false} />
                      <Tooltip {...tip} />
                      <Radar
                        name="میانگین"
                        dataKey="v"
                        stroke="var(--primary)"
                        fill="var(--primary)"
                        fillOpacity={0.35}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <div className="glass p-5">
              <h3 className="mb-2 font-bold">روند میانگین نمرات</h3>
              <div className="h-72" dir="ltr">
                {line.length === 0 ? (
                  <div className="grid h-full place-items-center text-sm text-muted-foreground">
                    داده‌ای برای نمودار موجود نیست.
                  </div>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={line} margin={{ left: -20, right: 10 }}>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="m"
                        reversed
                        tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                      />
                      <YAxis
                        orientation="right"
                        domain={[0, 20]}
                        tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                      />
                      <Tooltip {...tip} />
                      <Line
                        dataKey="a"
                        name="میانگین نمرات"
                        stroke="var(--primary)"
                        strokeWidth={3}
                        dot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <div className="glass p-5">
              <h3 className="mb-3 flex items-center gap-2 font-bold">
                <Trophy className="size-4 text-gold" /> دانش‌آموزان برتر
              </h3>
              {top.length === 0 ? (
                <p className="text-sm text-muted-foreground">هنوز نمره‌ای ثبت نشده است.</p>
              ) : (
                <ul className="space-y-3">
                  {top.map((s, i) => (
                    <li key={s.id} className="flex items-center gap-3 rounded-xl bg-muted/50 p-2.5">
                      <span
                        className={`grid size-8 place-items-center rounded-lg text-sm font-bold ${i === 0 ? "bg-gold text-background" : "bg-indigo-deep text-primary"}`}
                      >
                        {faNum(i + 1)}
                      </span>
                      <div className="flex-1">
                        <div className="text-sm font-bold">{s.name}</div>
                        <div className="text-xs text-muted-foreground">پایه {faNum(s.grade)}</div>
                      </div>
                      <span className="w-8 text-sm font-bold text-gold">
                        {s.gpa === null ? "—" : faNum(s.gpa)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-3">
            {badges.map(({ t, d, I }) => (
              <div
                key={t}
                className="glass group flex items-center gap-4 bg-gradient-to-l from-indigo-deep/60 to-transparent p-5 transition hover:border-gold/50"
              >
                <span className="grid size-14 place-items-center rounded-2xl bg-gold/15 text-gold ring-1 ring-gold/40 transition group-hover:scale-110">
                  <I className="size-7" />
                </span>
                <div>
                  <div className="font-bold">{t}</div>
                  <div className="text-sm text-muted-foreground">{d}</div>
                </div>
              </div>
            ))}
          </section>
        </main>
      </div>
    </div>
  );
}
