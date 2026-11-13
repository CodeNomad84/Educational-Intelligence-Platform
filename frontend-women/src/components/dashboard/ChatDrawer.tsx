import * as DialogPrimitive from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp,
  BookOpen,
  Building2,
  Check,
  Copy,
  GraduationCap,
  HeartHandshake,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import type { Citation, MentorRole } from "@/lib/mentor-chat.functions";
import { cn } from "@/lib/utils";
import { useDashboard, type ChatMessage } from "./dashboard-context";
import { Mascot, STATE_LABEL } from "./Mascot";

const ROLES: { id: MentorRole; label: string; icon: typeof GraduationCap }[] = [
  { id: "teacher", label: "معلم", icon: GraduationCap },
  { id: "counselor", label: "مشاور", icon: HeartHandshake },
  { id: "principal", label: "مدیر", icon: Building2 },
];

const SUGGESTIONS: Record<MentorRole, string[]> = {
  teacher: [
    "دانش‌آموزان نیازمند توجه در درس ریاضی چه کسانی هستند و چه کنم؟",
    "برای تقویت کار گروهی در پایه هفتم یک فعالیت بازی‌وار پیشنهاد بده",
    "کدام دانش‌آموزان آماده نقش منتور همتا هستند؟",
  ],
  counselor: [
    "یاسین عباسی در کدام سطح مداخله است و جلسه با خانواده را چطور طراحی کنم؟",
    "برای هلیا جعفری که اعتمادبه‌نفسش پایین آمده چه برنامه‌ای پیشنهاد می‌کنی؟",
    "نسبت تشویق به هشدار در مشاهدات اخیر چطور است؟",
  ],
  principal: [
    "گزارش اجرایی این هفته را با اولویت‌های تصمیم‌گیری خلاصه کن",
    "محور کارآفرینی چرا ضعیف‌ترین است و چه سرمایه‌گذاری لازم است؟",
    "مقایسه پایه‌ها در شش محور شایستگی را در یک جدول بده",
  ],
};

const toLatin = (s: string) => s.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));

function prepareMarkdown(text: string) {
  return text.replace(
    /\[([0-9۰-۹]{1,2})\](?!\()/g,
    (_, n: string) => `[${toLatin(n)}](#cite-${toLatin(n)})`,
  );
}

function citedIndexes(text: string) {
  const set = new Set<number>();
  for (const m of text.matchAll(/\[([0-9۰-۹]{1,2})\]/g)) set.add(Number(toLatin(m[1] ?? "")));
  return set;
}

function CitationBadge({ citation, n }: { citation: Citation | undefined; n: string }) {
  const label = Number(n).toLocaleString("fa-IR");
  if (!citation) return <sup className="mx-0.5 text-primary-glow">[{label}]</sup>;
  return (
    <HoverCard openDelay={120}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          className="mx-0.5 inline-grid size-5 translate-y-[-2px] place-items-center rounded-md bg-primary/25 align-middle text-[11px] font-bold text-primary-glow transition-colors hover:bg-primary/45"
          aria-label={`منبع ${label}: ${citation.title}`}
        >
          {label}
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        dir="rtl"
        className="w-72 rounded-2xl border-border glass-strong text-start"
      >
        <p className="text-sm font-bold">{citation.title}</p>
        <p className="mt-0.5 text-xs text-primary-glow">{citation.source}</p>
        <p className="mt-2 text-xs leading-6 text-muted-foreground">{citation.snippet}</p>
      </HoverCardContent>
    </HoverCard>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const citations = message.citations ?? [];
  const used = citedIndexes(message.content);
  const shown = citations.filter((c) => used.has(c.index));

  if (message.error) {
    return (
      <div className="rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm leading-7 text-destructive">
        {message.content}
      </div>
    );
  }

  return (
    <div className="rounded-2xl rounded-ss-md border border-border bg-surface/80 px-4 py-3">
      <div className="md-answer">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children, ...rest }: ComponentPropsWithoutRef<"a">) => {
              if (href?.startsWith("#cite-")) {
                const n = href.slice(6);
                return (
                  <CitationBadge n={n} citation={citations.find((c) => c.index === Number(n))} />
                );
              }
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary-glow underline underline-offset-4"
                  {...rest}
                >
                  {children}
                </a>
              );
            },
          }}
        >
          {prepareMarkdown(message.content)}
        </ReactMarkdown>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {shown.length > 0 && (
          <>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <BookOpen className="size-3.5" />
              منابع:
            </span>
            {shown.map((c) => (
              <span
                key={c.index}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/60 px-2 py-0.5 text-[11px] text-muted-foreground"
              >
                <span className="font-bold text-primary-glow">
                  {c.index.toLocaleString("fa-IR")}
                </span>
                {c.title}
              </span>
            ))}
          </>
        )}
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(message.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="ms-auto inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
          {copied ? "کپی شد" : "کپی"}
        </button>
      </div>
    </div>
  );
}

export function ChatDrawer() {
  const { chatOpen, setChatOpen, messages, pending, role, setRole, send, clearChat, mascot } =
    useDashboard();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  const submit = () => {
    if (!draft.trim() || pending) return;
    void send(draft);
    setDraft("");
  };

  return (
    <DialogPrimitive.Root open={chatOpen} onOpenChange={setChatOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-background/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          dir="rtl"
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            inputRef.current?.focus();
          }}
          className="fixed inset-y-0 left-0 z-50 flex w-full flex-col border-e border-border bg-popover shadow-2xl duration-300 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-[600px]"
        >
          {/* Header */}
          <div className="relative overflow-hidden border-b border-border px-5 pb-4 pt-5">
            <div
              aria-hidden
              className="pointer-events-none absolute -top-20 start-10 size-56 rounded-full bg-primary/25 blur-3xl"
            />
            <div className="relative flex items-center gap-3">
              <Mascot state={mascot} size={64} />
              <div className="min-w-0 flex-1">
                <DialogPrimitive.Title className="text-lg font-extrabold">
                  رهنما · دستیار مربیگری و رشد
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="text-xs text-muted-foreground">
                  {STATE_LABEL[mascot]} · پاسخ‌ها از اسناد مدرسه و کارنامه ۳۶۰ با ارجاع
                </DialogPrimitive.Description>
              </div>
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={clearChat}
                  aria-label="گفت‌وگوی تازه"
                  className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <RotateCcw className="size-4" />
                </button>
              )}
              <DialogPrimitive.Close
                aria-label="بستن"
                className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="size-5" />
              </DialogPrimitive.Close>
            </div>

            <div
              role="radiogroup"
              aria-label="نقش شما"
              className="relative mt-4 grid grid-cols-3 gap-1 rounded-2xl border border-border bg-surface/70 p-1"
            >
              {ROLES.map((r) => {
                const Icon = r.icon;
                const active = role === r.id;
                return (
                  <button
                    key={r.id}
                    role="radio"
                    aria-checked={active}
                    onClick={() => setRole(r.id)}
                    className={cn(
                      "relative flex items-center justify-center gap-2 rounded-xl py-2 text-sm font-medium transition-colors",
                      active
                        ? "text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="role-pill"
                        className="absolute inset-0 rounded-xl bg-gradient-primary shadow-glow"
                        transition={{ type: "spring", stiffness: 400, damping: 32 }}
                      />
                    )}
                    <Icon className="relative size-4" />
                    <span className="relative">{r.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-5 py-5"
          >
            {messages.length === 0 && !pending && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  پیشنهادهایی برای نقش «{ROLES.find((r) => r.id === role)?.label}»:
                </p>
                {SUGGESTIONS[role].map((s, i) => (
                  <motion.button
                    key={s}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.06 }}
                    onClick={() => void send(s)}
                    className="block w-full rounded-2xl border border-border bg-surface/70 px-4 py-3 text-start text-sm leading-7 transition-colors hover:border-primary/50 hover:bg-accent"
                  >
                    {s}
                  </motion.button>
                ))}
              </div>
            )}

            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn("flex", m.role === "user" ? "justify-start" : "justify-end")}
                >
                  {m.role === "user" ? (
                    <div className="max-w-[85%] rounded-2xl rounded-se-md bg-gradient-primary px-4 py-2.5 text-sm leading-7 text-primary-foreground shadow-glow">
                      {m.content}
                    </div>
                  ) : (
                    <div className="w-full max-w-[95%]">
                      <AssistantMessage message={m} />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {pending && (
              <div className="flex justify-end">
                <div className="flex items-center gap-3 rounded-2xl border border-border bg-surface/80 px-4 py-3 text-sm text-muted-foreground">
                  <span className="flex gap-1" aria-hidden>
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="size-1.5 animate-typing rounded-full bg-primary-glow"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </span>
                  در حال جست‌وجو در اسناد و کارنامه‌ها…
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-border p-4">
            <div className="flex items-end gap-2 rounded-3xl border border-border bg-surface/80 p-2 ps-4 transition-colors focus-within:border-primary/60">
              <textarea
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={1}
                placeholder="سؤال خود را بنویسید…"
                aria-label="پیام به دستیار"
                className="max-h-36 min-h-[40px] flex-1 resize-none bg-transparent py-2 text-sm leading-7 outline-none placeholder:text-muted-foreground"
              />
              <button
                type="button"
                onClick={submit}
                disabled={!draft.trim() || pending}
                aria-label="ارسال"
                className="grid size-10 shrink-0 place-items-center rounded-full bg-gradient-primary text-primary-foreground shadow-glow transition-all hover:brightness-110 disabled:opacity-40 disabled:shadow-none"
              >
                <ArrowUp className="size-5" />
              </button>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Enter برای ارسال · Shift+Enter برای خط جدید
            </p>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
