import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, Sparkles } from "lucide-react";
import { useEffect } from "react";

import { useDashboard } from "./dashboard-context";
import { Mascot, STATE_LABEL } from "./Mascot";

const CHIPS = [
  { emoji: "🎯", label: "تحلیل شایستگی‌های مأموریت‌محور", prompt: "شایستگی‌های شش‌گانه مدرسه را تحلیل کن: ضعیف‌ترین و قوی‌ترین محورها کدام‌اند و برای تقویت محور ضعیف چه مأموریت‌هایی پیشنهاد می‌کنی؟", mood: "analytical" as const },
  { emoji: "📝", label: "ثبت مشاهده جدید برای پایه", prompt: "می‌خواهم برای پایه نهم یک مشاهده جدید ثبت کنم. طبق دستورالعمل، یک قالب مشاهده عینی و چند نمونه خوب برای تشویق و پیشنهاد رشد به من بده.", mood: "thinking" as const },
  { emoji: "📊", label: "گزارش پیشرفت هفتگی", prompt: "گزارش پیشرفت هفتگی مدرسه را با شاخص‌های کلیدی، دستاوردها و هشدارها خلاصه کن.", mood: "analytical" as const },
  { emoji: "💡", label: "پیشنهاد برنامه رشد انفرادی", prompt: "برای محمدرضا کاظمی یک برنامه رشد انفرادی ۶ هفته‌ای پیشنهاد بده که از علاقه او به فیزیک برای بهبود ریاضی استفاده کند.", mood: "thinking" as const },
];

const BUBBLE: Record<string, string> = {
  idle: "سلام! من رهنما هستم. امروز چطور کمکتان کنم؟ 🌱",
  thinking: "دارم اسناد مدرسه و کارنامه‌ها را مرور می‌کنم…",
  analytical: "عینک داده‌ام را زدم! الگوها را پیدا کردم.",
  celebrate: "آفرین! یک قدم دیگر در مسیر رشد 🎉",
};

export function HeroCompanion() {
  const { mascot, openChat, flashMascot } = useDashboard();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        openChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openChat]);

  return (
    <section id="top" aria-labelledby="hero-title" className="relative overflow-hidden rounded-[2rem] glass px-5 py-8 sm:px-10 sm:py-10">
      <div aria-hidden className="pointer-events-none absolute -top-24 start-1/3 size-80 rounded-full bg-primary/25 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 end-10 size-72 rounded-full bg-success/15 blur-3xl" />

      <div className="relative grid items-center gap-8 lg:grid-cols-[auto_1fr]">
        {/* Mascot */}
        <div className="flex flex-col items-center gap-3">
          <div className="relative">
            <AnimatePresence mode="wait">
              <motion.div
                key={mascot}
                initial={{ opacity: 0, y: 6, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.95 }}
                transition={{ duration: 0.25 }}
                className="absolute -top-4 left-1/2 z-10 w-56 -translate-x-1/2 rounded-2xl glass-strong px-4 py-2.5 text-center text-sm leading-7 shadow-pill"
              >
                {BUBBLE[mascot]}
              </motion.div>
            </AnimatePresence>
            <button
              type="button"
              onClick={() => openChat()}
              onMouseEnter={() => mascot === "idle" && flashMascot("analytical", 1800)}
              aria-label="گفت‌وگو با دستیار رهنما"
              className="mt-20 rounded-full transition-transform hover:scale-[1.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Mascot state={mascot} size={196} />
            </button>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs text-muted-foreground">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
            {STATE_LABEL[mascot]}
          </span>
        </div>

        {/* Greeting + command bar */}
        <div className="min-w-0">
          <p className="mb-2 text-sm font-medium text-primary-glow">سه‌شنبه، هفته سوم آبان · پایه نهم</p>
          <h1 id="hero-title" className="text-3xl font-black leading-[1.35] tracking-tight sm:text-4xl lg:text-[2.75rem]">
            <span className="text-gradient">سلام خانم رضایی، امروز کدام نهال را آبیاری کنیم؟</span>
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-8 text-muted-foreground">
            <strong className="font-semibold text-warning">۳ دانش‌آموز</strong> نیازمند توجه‌اند و{" "}
            <strong className="font-semibold text-success">۲ دستاورد تازه</strong> برای جشن گرفتن داریم.
          </p>

          <button
            type="button"
            onClick={() => openChat()}
            className="group mt-6 flex w-full items-center gap-3 rounded-full glass-strong p-2 ps-5 text-start shadow-pill ring-gradient transition-all hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Sparkles className="size-5 shrink-0 text-primary-glow" aria-hidden />
            <span className="min-w-0 flex-1 truncate py-2 text-sm text-muted-foreground sm:text-base">
              از دستیار مربیگری و رشد بپرسید (مثال: دانش‌آموزان نیازمند توجه در درس ریاضی...)
            </span>
            <kbd className="hidden rounded-md border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground sm:inline">/</kbd>
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-gradient-primary text-primary-foreground shadow-glow transition-transform group-hover:-translate-y-0.5">
              <ArrowUp className="size-5" aria-hidden />
            </span>
          </button>

          <div className="mt-4 flex flex-wrap gap-2">
            {CHIPS.map((c, i) => (
              <motion.button
                key={c.label}
                type="button"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.07 }}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => {
                  flashMascot(c.mood, 1500);
                  openChat(c.prompt);
                }}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-4 py-2 text-sm text-foreground transition-colors hover:border-primary/50 hover:bg-accent"
              >
                <span aria-hidden>{c.emoji}</span>
                {c.label}
              </motion.button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
