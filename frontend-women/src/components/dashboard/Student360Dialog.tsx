import {
  HeartHandshake,
  Lightbulb,
  MessageSquarePlus,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { faNum, formatPersianDate, type Observation, type StudentRow } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";
import { StatusBadge, StudentAvatar } from "./StudentRoster";

const OBS_ICON: Record<
  Observation["kind"],
  { icon: typeof HeartHandshake; cls: string; label: string }
> = {
  kudos: { icon: HeartHandshake, cls: "bg-primary/15 text-primary-glow", label: "تشویق" },
  suggestion: { icon: Lightbulb, cls: "bg-info/15 text-info", label: "پیشنهاد رشد" },
  alert: { icon: TriangleAlert, cls: "bg-warning/15 text-warning", label: "هشدار" },
};

interface Props {
  student: StudentRow | null;
  onOpenChange: (open: boolean) => void;
  onFeedback: (id: number) => void;
}

export function Student360Dialog({ student, onOpenChange, onFeedback }: Props) {
  const { openChat } = useDashboard();

  return (
    <Dialog open={!!student} onOpenChange={onOpenChange}>
      <DialogContent
        dir="rtl"
        className="scrollbar-thin max-h-[90vh] max-w-3xl overflow-y-auto rounded-3xl border-border glass-strong"
      >
        {student && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-4">
                <StudentAvatar student={student} size="lg" />
                <div className="text-start">
                  <DialogTitle className="text-xl font-extrabold">
                    کارنامه جامع ۳۶۰ — {student.name}
                  </DialogTitle>
                  <DialogDescription className="mt-1 flex flex-wrap items-center gap-2">
                    <span>
                      پایه {faNum(student.grade)} · کلاس {student.classroom}
                    </span>
                    <StatusBadge status={student.status} />
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-border bg-surface/60 p-3">
                <p className="text-xs text-muted-foreground">معدل کل</p>
                <p className="text-2xl font-black">
                  {student.gpa === null ? "—" : faNum(student.gpa)}
                </p>
              </div>
              <div className="rounded-2xl border border-border bg-surface/60 p-3">
                <p className="text-xs text-muted-foreground">نرخ حضور</p>
                <p
                  className={cn(
                    "text-2xl font-black",
                    student.attendance_rate !== null &&
                      student.attendance_rate < 80 &&
                      "text-warning",
                  )}
                >
                  {student.attendance_rate === null ? "—" : `${faNum(student.attendance_rate)}٪`}
                </p>
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-bold">مشاهدات و بازخوردهای مربیان</p>
              {student.observations.length === 0 ? (
                <p className="text-sm text-muted-foreground">هنوز مشاهده‌ای ثبت نشده است.</p>
              ) : (
                <ol className="space-y-2">
                  {student.observations.map((o, i) => {
                    const m = OBS_ICON[o.kind];
                    const Icon = m.icon;
                    return (
                      <li
                        key={i}
                        className="flex gap-3 rounded-2xl border border-border bg-surface/60 p-3"
                      >
                        <span
                          className={cn(
                            "grid size-9 shrink-0 place-items-center rounded-xl",
                            m.cls,
                          )}
                        >
                          <Icon className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm leading-7">{o.text}</p>
                          <p className="text-xs text-muted-foreground">
                            {m.label} · {o.mentor} · {formatPersianDate(o.date)}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="hero"
                size="pill"
                onClick={() => {
                  onOpenChange(false);
                  openChat(
                    `کارنامه ۳۶۰ ${student.name} را تحلیل کن: نقاط قوت، فرصت‌های رشد و یک برنامه رشد انفرادی کوتاه پیشنهاد بده.`,
                  );
                }}
              >
                <Sparkles /> تحلیل با رهنما
              </Button>
              <Button variant="glass" size="pill" onClick={() => onFeedback(student.id)}>
                <MessageSquarePlus /> ثبت بازخورد
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
