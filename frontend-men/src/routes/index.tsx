import { createFileRoute } from "@tanstack/react-router";
import {
  Sparkles,
  Send,
  Users,
  Rocket,
  ShieldCheck,
  FileText,
  Trophy,
  Zap,
  Handshake,
  TrendingUp,
} from "lucide-react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { useState } from "react";
import { AreaChart, Area } from "recharts";
import { MascotAssistant, type MascotMood } from "@/components/MascotAssistant";

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

const kpis = [
  { t: "دانش‌آموزان فعال", v: "۱,۲۴۸", d: "+۱۲٪", I: Users },
  { t: "پروژه‌های مأموریتی", v: "۸۶", d: "+۸ پروژه", I: Rocket },
  { t: "شاخص رشد و تاب‌آوری", v: "۷۸٪", d: "+۵.۴٪", I: ShieldCheck },
  { t: "گزارش‌های مداخله و مشاوره", v: "۲۱۴", d: "این ماه", I: FileText },
];
const radar = [
  { k: "رشد تحصیلی", v: 82 },
  { k: "تاب‌آوری", v: 74 },
  { k: "تعامل اجتماعی", v: 68 },
  { k: "انگیزه یادگیری", v: 88 },
  { k: "مهارت‌های زندگی", v: 71 },
];
const line = ["مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"].map((m, i) => ({
  m,
  a: [52, 58, 63, 67, 74, 81][i],
  b: [45, 50, 57, 61, 66, 72][i],
}));
const students = [
  { n: "امیرحسین رضایی", c: "پایه دهم", s: 96, b: "قهرمان مأموریت" },
  { n: "محمد کریمی", c: "پایه یازدهم", s: 93, b: "رهبر تیم" },
  { n: "علی احمدی", c: "پایه نهم", s: 90, b: "نوآور" },
  { n: "رضا محمدی", c: "پایه دهم", s: 88, b: "پرتلاش" },
  { n: "سینا حسینی", c: "پایه دوازدهم", s: 85, b: "تاب‌آور" },
];
const badges = [
  { t: "پیشرفت ممتاز در یادگیری", d: "۴۲ دانش‌آموز این ماه", I: Zap },
  { t: "رشد چشمگیر در تاب‌آوری", d: "افزایش ۱۸٪ نسبت به ترم قبل", I: TrendingUp },
  { t: "همکاری برتر در پروژه مأموریتی", d: "تیم رباتیک پایه یازدهم", I: Handshake },
];
const spark = (seed: string) =>
  Array.from({ length: 8 }, (_, i) => ({
    v: 40 + i * 6 + ((seed.charCodeAt(i % seed.length) * (i + 3)) % 18),
  }));
const tip = {
  contentStyle: {
    background: "var(--background)",
    border: "1px solid var(--border)",
    borderRadius: 12,
  },
};

function Index() {
  const [mood, setMood] = useState<MascotMood>("idle");
  const [q, setQ] = useState("");
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
              سال تحصیلی ۱۴۰۵
            </span>
          </header>

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
            {kpis.map(({ t, v, d, I }) => (
              <div key={t} className="glass p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t}</span>
                  <span className="rounded-lg bg-indigo-deep p-2 text-primary">
                    <I className="size-5" />
                  </span>
                </div>
                <div className="mt-3 text-3xl font-extrabold">{v}</div>
                <div className="mt-1 flex items-end justify-between gap-2">
                  <span className="text-xs text-gold">{d}</span>
                  <div className="h-8 w-20" dir="ltr">
                    <ResponsiveContainer>
                      <AreaChart data={spark(t)}>
                        <Area
                          dataKey="v"
                          stroke="var(--primary)"
                          fill="var(--primary)"
                          fillOpacity={0.2}
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            ))}
          </section>

          <section className="grid gap-4 lg:grid-cols-3">
            <div className="glass p-5">
              <h3 className="mb-2 font-bold">وضعیت رشد چندبعدی</h3>
              <div className="h-72">
                <ResponsiveContainer>
                  <RadarChart data={radar} outerRadius="70%">
                    <PolarGrid stroke="var(--border)" />
                    <PolarAngleAxis
                      dataKey="k"
                      tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                    />
                    <Tooltip {...tip} />
                    <Radar
                      name="امتیاز"
                      dataKey="v"
                      stroke="var(--primary)"
                      fill="var(--primary)"
                      fillOpacity={0.35}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="glass p-5">
              <h3 className="mb-2 font-bold">روند رشد در طول زمان</h3>
              <div className="h-72" dir="ltr">
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
                      tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                    />
                    <Tooltip {...tip} />
                    <Line
                      dataKey="a"
                      name="رشد کلی"
                      stroke="var(--primary)"
                      strokeWidth={3}
                      dot={{ r: 4 }}
                    />
                    <Line
                      dataKey="b"
                      name="تاب‌آوری"
                      stroke="var(--gold)"
                      strokeWidth={2}
                      strokeDasharray="5 4"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="glass p-5">
              <h3 className="mb-3 flex items-center gap-2 font-bold">
                <Trophy className="size-4 text-gold" /> دانش‌آموزان برتر
              </h3>
              <ul className="space-y-3">
                {students.map((s, i) => (
                  <li key={s.n} className="flex items-center gap-3 rounded-xl bg-muted/50 p-2.5">
                    <span
                      className={`grid size-8 place-items-center rounded-lg text-sm font-bold ${i === 0 ? "bg-gold text-background" : "bg-indigo-deep text-primary"}`}
                    >
                      {(i + 1).toLocaleString("fa")}
                    </span>
                    <div className="flex-1">
                      <div className="text-sm font-bold">{s.n}</div>
                      <div className="text-xs text-muted-foreground">{s.c}</div>
                    </div>
                    <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                      {s.b}
                    </span>
                    <span className="w-8 text-sm font-bold text-gold">
                      {s.s.toLocaleString("fa")}
                    </span>
                  </li>
                ))}
              </ul>
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
