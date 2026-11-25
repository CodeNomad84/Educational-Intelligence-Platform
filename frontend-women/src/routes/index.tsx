import { createFileRoute } from "@tanstack/react-router";
import { LogIn } from "lucide-react";

import { ChatDrawer } from "@/components/dashboard/ChatDrawer";
import { CompetencyRadar } from "@/components/dashboard/CompetencyRadar";
import { DashboardProvider, useDashboard } from "@/components/dashboard/dashboard-context";
import { GrowthStream } from "@/components/dashboard/GrowthStream";
import { HeroCompanion } from "@/components/dashboard/HeroCompanion";
import { KpiStrip } from "@/components/dashboard/KpiStrip";
import { StudentRoster } from "@/components/dashboard/StudentRoster";
import { TopBar } from "@/components/dashboard/TopBar";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "داشبورد رشد و شکوفایی | آرمان‌نو - نسیم" },
      {
        name: "description",
        content:
          "پایش شایستگی‌های شش‌گانه، تابلوی رشد متربیان و دستیار هوشمند مربیگری مأموریت‌محور در سکوی آرمان‌نو - نسیم.",
      },
      { property: "og:title", content: "سکوی آرمان‌نو - نسیم" },
      {
        property: "og:description",
        content:
          "پایش شایستگی‌ها، تابلوی رشد و دستیار هوشمند مربیگری برای معلمان، مشاوران و مدیران — سکوی آرمان‌نو - نسیم.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function DashboardBanner() {
  const { loading, error, me } = useDashboard();
  if (loading) {
    return (
      <p className="rounded-2xl border border-border bg-surface/60 px-4 py-3 text-center text-sm text-muted-foreground">
        در حال دریافت داده‌های زنده از سامانه…
      </p>
    );
  }
  if (error) {
    return (
      <p className="rounded-2xl border border-warning/40 bg-warning/10 px-4 py-3 text-center text-sm text-warning">
        دریافت داده‌ها ممکن نشد: {error}
      </p>
    );
  }
  if (!me) {
    return (
      <section className="rounded-[2rem] glass p-6 text-center sm:p-8">
        <h2 className="text-xl font-black">
          <span className="text-gradient">برای مشاهده تابلوی رشد وارد شوید</span>
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          داده‌های زنده، تابلوی رشد متربیان و دستیار هوشمند مربیگری پس از ورود به حساب کاربری نمایش
          داده می‌شود.
        </p>
        <a
          href="/login"
          className="mt-5 inline-flex items-center gap-2 rounded-full bg-gradient-primary px-5 py-2.5 font-bold text-primary-foreground shadow-glow transition hover:brightness-110"
        >
          <LogIn className="size-4" aria-hidden />
          ورود به سامانه
        </a>
      </section>
    );
  }
  return null;
}

function Index() {
  return (
    <DashboardProvider>
      <div className="min-h-screen">
        <TopBar />
        <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          <DashboardBanner />
          <HeroCompanion />
          <KpiStrip />
          <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr]">
            <CompetencyRadar />
            <GrowthStream />
          </div>
          <StudentRoster />
        </main>
        <footer className="mx-auto max-w-7xl px-6 pb-10 pt-2 text-center text-xs text-muted-foreground">
          سکوی آموزشی-تربیتی آرمان‌نو - شاخه نسیم · سامانه رشد و انتخاب مأموریت‌محور — داده‌های زنده
          از سامانه
        </footer>
      </div>
      <ChatDrawer />
    </DashboardProvider>
  );
}
