import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CalendarCheck, CheckCircle2, ChevronDown, HeartHandshake, PartyPopper, Sparkles, Trophy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { StreamItem, StreamKind } from "@/data/school";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";

const KIND: Record<StreamKind, { label: string; icon: typeof Trophy; chip: string; rail: string }> = {
  milestone: { label: "دستاورد", icon: Trophy, chip: "bg-success/15 text-success", rail: "bg-success" },
  kudos: { label: "تشویق معلم", icon: HeartHandshake, chip: "bg-primary/15 text-primary-glow", rail: "bg-primary-glow" },
  alert: { label: "هشدار مشاور", icon: AlertTriangle, chip: "bg-warning/15 text-warning", rail: "bg-warning" },
};

const FILTERS: { id: "all" | StreamKind; label: string }[] = [
  { id: "all", label: "همه" },
  { id: "milestone", label: "دستاوردها" },
  { id: "kudos", label: "تشویق‌ها" },
  { id: "alert", label: "هشدارها" },
];

export function GrowthStream() {
  const { stream, openChat, flashMascot, students } = useDashboard();
  const [filter, setFilter] = useState<"all" | StreamKind>("all");
  const [expanded, setExpanded] = useState<string | null>(stream[0]?.id ?? null);
  const [handled, setHandled] = useState<Record<string, boolean>>({});

  const items = stream.filter((s) => filter === "all" || s.kind === filter);
  const alertsOpen = stream.filter((s) => s.kind === "alert" && !handled[s.id]).length;

  const studentName = (item: StreamItem) => students.find((s) => s.id === item.studentId)?.name ?? "";

  return (
    <section id="stream" aria-labelledby="stream-title" className="flex scroll-mt-24 flex-col rounded-3xl glass p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="stream-title" className="text-lg font-extrabold">تابلوی رشد و پایش مسیر مأموریت</h2>
          <p className="text-sm text-muted-foreground">
            دستاوردها، تشویق‌ها و هشدارهای تازه ·{" "}
            <span className="font-semibold text-warning">{alertsOpen.toLocaleString("fa-IR")} هشدار باز</span>
          </p>
        </div>
        <div role="tablist" aria-label="فیلتر رویدادها" className="flex gap-1 rounded-full border border-border bg-surface/60 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                filter === f.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <ul className="scrollbar-thin mt-4 -me-2 max-h-[520px] space-y-3 overflow-y-auto pe-2">
        <AnimatePresence initial={false}>
          {items.map((item) => {
            const meta = KIND[item.kind];
            const Icon = meta.icon;
            const open = expanded === item.id;
            const isHandled = handled[item.id];
            return (
              <motion.li
                key={item.id}
                layout
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97 }}
                className={cn(
                  "relative overflow-hidden rounded-2xl border border-border bg-surface/70 transition-colors hover:border-primary/40",
                  isHandled && "opacity-70",
                )}
              >
                <span aria-hidden className={cn("absolute inset-y-3 start-0 w-1 rounded-full", meta.rail)} />
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : item.id)}
                  aria-expanded={open}
                  className="flex w-full items-start gap-3 p-4 ps-5 text-start"
                >
                  <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", meta.chip)}>
                    <Icon className="size-5" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className={cn("rounded-full px-2 py-0.5 font-semibold", meta.chip)}>{meta.label}</span>
                      <span>{item.tag}</span>
                      <span>·</span>
                      <span>{item.time}</span>
                      {isHandled && (
                        <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="size-3" />پیگیری شد</span>
                      )}
                    </span>
                    <span className="mt-1 block font-bold leading-7">{item.title}</span>
                  </span>
                  <ChevronDown className={cn("mt-2 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
                </button>
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-4">
                        <p className="text-sm leading-7 text-muted-foreground">{item.body}</p>
                        <p className="mt-1 text-xs text-muted-foreground">ثبت توسط {item.author}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.kind === "alert" ? (
                            <Button
                              size="sm"
                              variant="warning"
                              disabled={isHandled}
                              onClick={() => {
                                setHandled((h) => ({ ...h, [item.id]: true }));
                                toast.success("جلسه پیگیری برنامه‌ریزی شد", { description: `${studentName(item)} — فردا، زنگ دوم` });
                              }}
                            >
                              <CalendarCheck /> برنامه‌ریزی جلسه
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="success"
                              onClick={() => {
                                flashMascot("celebrate");
                                toast.success("پیام تبریک ارسال شد 🎉", { description: `برای ${studentName(item)} و خانواده‌اش` });
                              }}
                            >
                              <PartyPopper /> ارسال تبریک
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="soft"
                            onClick={() =>
                              openChat(
                                item.kind === "alert"
                                  ? `برای این هشدار چه مداخله‌ای پیشنهاد می‌کنی؟ «${item.title}: ${item.body}»`
                                  : `چطور این دستاورد را به گام بعدی رشد تبدیل کنیم؟ «${item.title}: ${item.body}»`,
                              )
                            }
                          >
                            <Sparkles /> بپرس از رهنما
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
    </section>
  );
}
