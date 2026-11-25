import { HeartHandshake, Lightbulb, Send, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { Observation, StudentRow } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useDashboard } from "./dashboard-context";

const KINDS: {
  id: Observation["kind"];
  label: string;
  icon: typeof HeartHandshake;
  active: string;
}[] = [
  {
    id: "kudos",
    label: "تشویق",
    icon: HeartHandshake,
    active: "border-primary/60 bg-primary/20 text-primary-glow",
  },
  {
    id: "suggestion",
    label: "پیشنهاد رشد",
    icon: Lightbulb,
    active: "border-info/60 bg-info/15 text-info",
  },
  {
    id: "alert",
    label: "هشدار",
    icon: TriangleAlert,
    active: "border-warning/60 bg-warning/15 text-warning",
  },
];

export function FeedbackDialog({
  student,
  onOpenChange,
}: {
  student: StudentRow | null;
  onOpenChange: (o: boolean) => void;
}) {
  const { addObservation, me } = useDashboard();
  const [kind, setKind] = useState<Observation["kind"]>("kudos");
  const [text, setText] = useState("");

  useEffect(() => {
    if (student) {
      setKind("kudos");
      setText("");
    }
  }, [student]);

  const submit = () => {
    if (!student || text.trim().length < 8) return;
    addObservation(student.id, {
      kind,
      text: text.trim(),
      mentor: me?.display_name ?? "مربی",
      date: null,
    });
    toast.success("بازخورد ثبت شد 🌱", {
      description: `در تابلوی رشد نمایش داده می‌شود.`,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={!!student} onOpenChange={onOpenChange}>
      <DialogContent dir="rtl" className="max-w-lg rounded-3xl border-border glass-strong">
        {student && (
          <>
            <DialogHeader>
              <DialogTitle className="text-lg font-extrabold">
                ثبت بازخورد برای {student.name}
              </DialogTitle>
              <DialogDescription>
                مشاهده را عینی و رفتاری بنویسید: چه دیدید، کجا و چه زمانی.
              </DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="نوع بازخورد">
              {KINDS.map((k) => {
                const Icon = k.icon;
                return (
                  <button
                    key={k.id}
                    role="radio"
                    aria-checked={kind === k.id}
                    onClick={() => setKind(k.id)}
                    className={cn(
                      "flex flex-col items-center gap-1.5 rounded-2xl border p-3 text-sm transition-colors",
                      kind === k.id
                        ? k.active
                        : "border-border text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Icon className="size-5" />
                    {k.label}
                  </button>
                );
              })}
            </div>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              placeholder="مثال: امروز در کلاس ریاضی داوطلبانه راه‌حل معادله را برای هم‌گروهی‌اش توضیح داد."
              aria-label="متن بازخورد"
              className="rounded-2xl bg-surface/70 leading-7"
            />
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {text.trim().length < 8 ? "حداقل ۸ نویسه" : "آماده ثبت"}
              </span>
              <Button variant="hero" size="pill" disabled={text.trim().length < 8} onClick={submit}>
                <Send className="rtl:-scale-x-100" /> ثبت بازخورد
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
