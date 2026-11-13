import { HeartHandshake, Lightbulb, MessageSquarePlus, Sparkles, TriangleAlert } from "lucide-react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { COMPETENCY_AXES, RADAR_BY_GRADE, type Observation, type Student } from "@/data/school";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";
import { StatusBadge, StudentAvatar, TRACK_COLOR } from "./StudentRoster";

const OBS_ICON: Record<Observation["kind"], { icon: typeof HeartHandshake; cls: string; label: string }> = {
  kudos: { icon: HeartHandshake, cls: "bg-primary/15 text-primary-glow", label: "تشویق" },
  suggestion: { icon: Lightbulb, cls: "bg-info/15 text-info", label: "پیشنهاد رشد" },
  alert: { icon: TriangleAlert, cls: "bg-warning/15 text-warning", label: "هشدار" },
};

interface Props {
  student: Student | null;
  onOpenChange: (open: boolean) => void;
  onFeedback: (id: string) => void;
}

export function Student360Dialog({ student, onOpenChange, onFeedback }: Props) {
  const { openChat } = useDashboard();
  const gradeAvg = student ? RADAR_BY_GRADE[student.grade] : null;
  const data = student && gradeAvg
    ? COMPETENCY_AXES.map((a) => ({ axis: a.label, me: student.competencies[a.key], avg: gradeAvg[a.key] }))
    : [];

  return (
    <Dialog open={!!student} onOpenChange={onOpenChange}>
      <DialogContent dir="rtl" className="scrollbar-thin max-h-[90vh] max-w-3xl overflow-y-auto rounded-3xl border-border glass-strong">
        {student && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-4">
                <StudentAvatar student={student} size="lg" />
                <div className="text-start">
                  <DialogTitle className="text-xl font-extrabold">کارنامه جامع ۳۶۰ — {student.name}</DialogTitle>
                  <DialogDescription className="mt-1 flex flex-wrap items-center gap-2">
                    <span>پایه {student.grade} · کلاس {student.classroom}</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs", TRACK_COLOR[student.track])}>{student.track}</span>
                    <StatusBadge status={student.status} />
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="grid gap-4 md:grid-cols-[1.1fr_1fr]">
              <div className="rounded-2xl border border-border bg-surface/60 p-3">
                <p className="text-sm font-bold">پروفایل شایستگی</p>
                <div className="h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={data} outerRadius="70%">
                      <PolarGrid stroke="var(--border)" />
                      <PolarAngleAxis dataKey="axis" tick={{ fill: "var(--foreground)", fontSize: 12, fontFamily: "inherit" }} />
                      <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                      <Radar dataKey="avg" stroke="var(--muted-foreground)" strokeDasharray="4 4" fill="var(--muted-foreground)" fillOpacity={0.08} />
                      <Radar dataKey="me" stroke="var(--primary-glow)" strokeWidth={2.5} fill="var(--primary)" fillOpacity={0.35} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-primary-glow" />{student.name.split(" ")[0]}</span>
                  <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-muted-foreground" />میانگین پایه</span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-border bg-surface/60 p-3">
                    <p className="text-xs text-muted-foreground">معدل کل</p>
                    <p className="text-2xl font-black">{student.gpa.toLocaleString("fa-IR")}</p>
                  </div>
                  <div className="rounded-2xl border border-border bg-surface/60 p-3">
                    <p className="text-xs text-muted-foreground">ریاضی</p>
                    <p className={cn("text-2xl font-black", student.mathScore < 12 && "text-warning")}>{student.mathScore.toLocaleString("fa-IR")}</p>
                  </div>
                </div>
                <div className="space-y-2">
                  {COMPETENCY_AXES.map((a) => {
                    const v = student.competencies[a.key];
                    return (
                      <div key={a.key}>
                        <div className="flex justify-between text-xs">
                          <span>{a.label}</span>
                          <span className="text-muted-foreground">{v.toLocaleString("fa-IR")}</span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn("h-full rounded-full", v >= 85 ? "bg-gradient-growth" : v < 60 ? "bg-gradient-warm" : "bg-gradient-primary")}
                            style={{ width: `${v}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-bold">مشاهدات مربیان</p>
              <ol className="space-y-2">
                {student.observations.map((o, i) => {
                  const m = OBS_ICON[o.kind];
                  const Icon = m.icon;
                  return (
                    <li key={i} className="flex gap-3 rounded-2xl border border-border bg-surface/60 p-3">
                      <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl", m.cls)}><Icon className="size-4" /></span>
                      <div className="min-w-0">
                        <p className="text-sm leading-7">{o.text}</p>
                        <p className="text-xs text-muted-foreground">{m.label} · {o.mentor} · {o.date}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="hero"
                size="pill"
                onClick={() => {
                  onOpenChange(false);
                  openChat(`کارنامه ۳۶۰ ${student.name} را تحلیل کن: نقاط قوت، فرصت‌های رشد و یک برنامه رشد انفرادی کوتاه پیشنهاد بده.`);
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
