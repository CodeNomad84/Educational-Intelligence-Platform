import { createFileRoute } from "@tanstack/react-router";

import { ChatDrawer } from "@/components/dashboard/ChatDrawer";
import { CompetencyRadar } from "@/components/dashboard/CompetencyRadar";
import { DashboardProvider } from "@/components/dashboard/dashboard-context";
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

function Index() {
  return (
    <DashboardProvider>
      <div className="min-h-screen">
        <TopBar />
        <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          <HeroCompanion />
          <KpiStrip />
          <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr]">
            <CompetencyRadar />
            <GrowthStream />
          </div>
          <StudentRoster />
        </main>
        <footer className="mx-auto max-w-7xl px-6 pb-10 pt-2 text-center text-xs text-muted-foreground">
          سکوی آموزشی-تربیتی آرمان‌نو - شاخه نسیم · سامانه رشد و انتخاب مأموریت‌محور — داده‌های
          نمایشی
        </footer>
      </div>
      <ChatDrawer />
    </DashboardProvider>
  );
}
