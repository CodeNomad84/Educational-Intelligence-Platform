import * as DialogPrimitive from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp,
  Building2,
  Check,
  Copy,
  GraduationCap,
  HeartHandshake,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { MENTOR_ROLES, mentorRolesFor, type MentorRole } from "@/lib/mentor-chat";
import { cn } from "@/lib/utils";
import { useDashboard, type ChatMessage } from "./dashboard-context";
import { Mascot, STATE_LABEL } from "./Mascot";

const ROLE_ICONS: Record<MentorRole, typeof GraduationCap> = {
  teacher: GraduationCap,
  counselor: HeartHandshake,
  principal: Building2,
};

const SUGGESTIONS: Record<MentorRole, string[]> = {
  teacher: [
    "برای تقویت کار گروهی در کلاس یک فعالیت بازی‌وار پیشنهاد بده",
    "چطور می‌توانم بازخورد روزانه مؤثرتری به دانش‌آموزان بدهم؟",
    "یک قالب مشاهده عینی برای ثبت رفتار در کلاس به من بده",
  ],
  counselor: [
    "برای یک جلسه گفت‌وگو با خانواده چه ساختاری پیشنهاد می‌کنی؟",
    "برای تقویت اعتمادبه‌نفس یک دانش‌آموز چه برنامه‌ای پیشنهاد می‌کنی؟",
    "نسبت تشویق به هشدار در مشاهدات باید چقدر باشد؟",
  ],
  principal: [
    "اولویت‌های تصمیم‌گیری این هفته را چطور تعیین کنم؟",
    "برای تقویت محور کارآفرینی چه سرمایه‌گذاری‌هایی لازم است؟",
    "یک گزارش اجرایی هفتگی را چطور خلاصه کنم؟",
  ],
};

function AssistantMessage({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);

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
            a: ({ href, children, ...rest }: ComponentPropsWithoutRef<"a">) => (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-primary-glow underline underline-offset-4"
                {...rest}
              >
                {children}
              </a>
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
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
  const {
    chatOpen,
    setChatOpen,
    messages,
    pending,
    role,
    setRole,
    send,
    clearChat,
    mascot,
    aiStatus,
    me,
  } = useDashboard();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const availableRoles = useMemo<MentorRole[]>(() => mentorRolesFor(me?.roles ?? []), [me]);
  const visibleRoles = useMemo(
    () => MENTOR_ROLES.filter((r) => availableRoles.includes(r.id)),
    [availableRoles],
  );
  const aiDisabled = aiStatus !== null && !aiStatus.enabled;
  const noRoles = availableRoles.length === 0;
  const roleLabel = MENTOR_ROLES.find((r) => r.id === role)?.label ?? "";
  const roleGridCols =
    visibleRoles.length === 1
      ? "grid-cols-1"
      : visibleRoles.length === 2
        ? "grid-cols-2"
        : "grid-cols-3";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  const submit = () => {
    if (!draft.trim() || pending || aiDisabled || noRoles) return;
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
                  {STATE_LABEL[mascot]} · دستیار هوشمند مربیگری و رشد
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

            {visibleRoles.length > 0 && (
              <div
                role="radiogroup"
                aria-label="نقش شما"
                className={cn(
                  "relative mt-4 grid gap-1 rounded-2xl border border-border bg-surface/70 p-1",
                  roleGridCols,
                )}
              >
                {visibleRoles.map((r) => {
                  const Icon = ROLE_ICONS[r.id];
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
            )}
          </div>

          {aiStatus && !aiStatus.enabled && (
            <div className="border-b border-border bg-warning/10 px-5 py-3">
              <p className="text-sm leading-7 text-warning">
                <strong>ابزار هوش مصنوعی فعال نیست.</strong> {aiStatus.detail}
              </p>
            </div>
          )}

          {/* Messages */}
          <div
            ref={scrollRef}
            className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-5 py-5"
          >
            {messages.length === 0 && !pending && !aiDisabled && !noRoles && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">پیشنهادهایی برای نقش «{roleLabel}»:</p>
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
                  در حال دریافت پاسخ…
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
                disabled={aiDisabled || noRoles}
                placeholder={
                  aiDisabled || noRoles ? "ابزار هوش مصنوعی در دسترس نیست" : "سؤال خود را بنویسید…"
                }
                aria-label="پیام به دستیار"
                className="max-h-36 min-h-[40px] flex-1 resize-none bg-transparent py-2 text-sm leading-7 outline-none placeholder:text-muted-foreground disabled:opacity-50"
              />
              <button
                type="button"
                onClick={submit}
                disabled={!draft.trim() || pending || aiDisabled || noRoles}
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
