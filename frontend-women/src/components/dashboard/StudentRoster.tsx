import { FileBarChart2, MessageSquarePlus, Search, Users } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  faNum,
  formatPersianDate,
  STATUS_META,
  type AcademicStatus,
  type StudentRow,
} from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";
import { FeedbackDialog } from "./FeedbackDialog";
import { Student360Dialog } from "./Student360Dialog";

const TONE_TO_BADGE = {
  success: "success",
  info: "info",
  warning: "warning",
  destructive: "danger",
} as const;

export function StatusBadge({ status }: { status: AcademicStatus }) {
  const meta = STATUS_META[status];
  return <Badge variant={TONE_TO_BADGE[meta.tone]}>{meta.label}</Badge>;
}

export function StudentAvatar({
  student,
  size = "md",
}: {
  student: StudentRow;
  size?: "md" | "lg";
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center rounded-full font-bold bg-primary/20 text-primary-glow",
        size === "lg" ? "size-14 text-xl" : "size-9 text-sm",
      )}
    >
      {student.name.charAt(0)}
    </span>
  );
}

export function StudentRoster() {
  const { students, summary } = useDashboard();
  const [query, setQuery] = useState("");
  const [grade, setGrade] = useState<string>("all");
  const [status, setStatus] = useState<"all" | AcademicStatus>("all");
  const [profileId, setProfileId] = useState<number | null>(null);
  const [feedbackId, setFeedbackId] = useState<number | null>(null);

  const grades = summary?.grades_present ?? [];

  const filtered = useMemo(
    () =>
      students.filter(
        (s) =>
          (grade === "all" || String(s.grade) === grade) &&
          (status === "all" || s.status === status) &&
          (query.trim() === "" ||
            s.name.includes(query.trim()) ||
            s.classroom.includes(query.trim())),
      ),
    [students, grade, status, query],
  );

  const profile = students.find((s) => s.id === profileId) ?? null;
  const feedbackStudent = students.find((s) => s.id === feedbackId) ?? null;

  return (
    <section
      id="roster"
      aria-labelledby="roster-title"
      className="scroll-mt-24 rounded-3xl glass p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="roster-title" className="flex items-center gap-2 text-lg font-extrabold">
            <Users className="size-5 text-primary-glow" /> فهرست متربیان
          </h2>
          <p className="text-sm text-muted-foreground">
            {faNum(filtered.length)} از {faNum(students.length)} دانش‌آموز
          </p>
        </div>
        <div className="flex w-full flex-wrap gap-2 lg:w-auto">
          <div className="relative min-w-[220px] flex-1 lg:w-64 lg:flex-none">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="جست‌وجوی نام یا کلاس…"
              aria-label="جست‌وجوی دانش‌آموز"
              className="h-10 rounded-full bg-surface/70 ps-9"
            />
          </div>
          <Select value={grade} onValueChange={setGrade}>
            <SelectTrigger
              aria-label="فیلتر پایه"
              className="h-10 w-[130px] rounded-full bg-surface/70"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">همه پایه‌ها</SelectItem>
              {grades.map((g) => (
                <SelectItem key={g} value={String(g)}>
                  پایه {faNum(g)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="فیلتر وضعیت تحصیلی">
        {(["all", "excellent", "growing", "attention", "risk"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            aria-pressed={status === s}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              status === s
                ? "border-primary/60 bg-primary/20 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "all" ? "همه وضعیت‌ها" : STATUS_META[s].label}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-2xl border border-border">
        <Table className="min-w-[920px]">
          <TableHeader>
            <TableRow className="bg-surface/80 hover:bg-surface/80">
              <TableHead className="ps-4">نام دانش‌آموز</TableHead>
              <TableHead>پایه / کلاس</TableHead>
              <TableHead>وضعیت تحصیلی</TableHead>
              <TableHead>آخرین مشاهده مربی</TableHead>
              <TableHead className="pe-4 text-end">اقدامات</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((s) => {
              const obs = s.observations[0];
              return (
                <TableRow key={s.id} className="border-border transition-colors hover:bg-accent/40">
                  <TableCell className="ps-4">
                    <div className="flex items-center gap-3">
                      <StudentAvatar student={s} />
                      <div>
                        <p className="font-semibold">{s.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {s.gpa === null ? "بدون نمره" : `معدل ${faNum(s.gpa)}`}
                        </p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {faNum(s.grade)} · <span className="text-foreground">{s.classroom}</span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={s.status} />
                  </TableCell>
                  <TableCell className="max-w-[280px]">
                    <p className="truncate text-sm" title={obs?.text}>
                      {obs?.text ?? "—"}
                    </p>
                    {obs && (
                      <p className="text-xs text-muted-foreground">
                        {obs.mentor} · {formatPersianDate(obs.date)}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="pe-4">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="soft" onClick={() => setProfileId(s.id)}>
                        <FileBarChart2 /> کارنامه جامع ۳۶۰
                      </Button>
                      <Button size="sm" variant="glass" onClick={() => setFeedbackId(s.id)}>
                        <MessageSquarePlus /> ثبت بازخورد
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                  دانش‌آموزی با این فیلترها پیدا نشد.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Student360Dialog
        student={profile}
        onOpenChange={(o) => !o && setProfileId(null)}
        onFeedback={(id) => {
          setProfileId(null);
          setFeedbackId(id);
        }}
      />
      <FeedbackDialog student={feedbackStudent} onOpenChange={(o) => !o && setFeedbackId(null)} />
    </section>
  );
}
