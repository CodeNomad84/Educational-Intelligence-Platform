import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useServerFn } from "@tanstack/react-start";

import { apiMe, ApiError, type MeResponse } from "@/lib/api";
import {
  buildStream,
  faNum,
  fetchDashboardSummary,
  formatPersianDate,
  type DashboardSummary,
  type Observation,
  type StreamItem,
  type StudentRow,
} from "@/lib/dashboard";
import { askMentor, type Citation, type MentorRole } from "@/lib/mentor-chat.functions";

export type MascotState = "idle" | "thinking" | "analytical" | "celebrate";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  error?: boolean;
}

interface DashboardContextValue {
  mascot: MascotState;
  flashMascot: (state: MascotState, ms?: number) => void;
  setMascotHold: (state: MascotState | null) => void;

  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
  openChat: (prompt?: string) => void;
  messages: ChatMessage[];
  pending: boolean;
  role: MentorRole;
  setRole: (role: MentorRole) => void;
  send: (text: string) => Promise<void>;
  clearChat: () => void;

  summary: DashboardSummary | null;
  loading: boolean;
  error: string | null;
  me: MeResponse | null;
  students: StudentRow[];
  stream: StreamItem[];
  addObservation: (studentId: number, obs: Observation) => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

let idCounter = 0;
const uid = (p: string) => `${p}-${Date.now().toString(36)}-${(idCounter++).toString(36)}`;

const OBS_KIND_LABEL: Record<Observation["kind"], string> = {
  kudos: "تشویق",
  suggestion: "پیشنهاد رشد",
  alert: "هشدار",
};

export function DashboardProvider({ children }: { children: ReactNode }) {
  const ask = useServerFn(askMentor);

  const [flash, setFlash] = useState<MascotState | null>(null);
  const [hold, setMascotHold] = useState<MascotState | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [role, setRole] = useState<MentorRole>("teacher");

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<StreamItem[]>([]);
  const [notes, setNotes] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [nextSummary, nextMe] = await Promise.all([fetchDashboardSummary(), apiMe()]);
        if (cancelled) return;
        setSummary(nextSummary);
        setMe(nextMe);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401 && typeof window !== "undefined") {
          window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname)}`);
          return;
        }
        setError(err instanceof Error ? err.message : "خطا در دریافت داده‌ها");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const flashMascot = useCallback((state: MascotState, ms = 2600) => {
    if (flashTimer.current) clearTimeout(flashTimer.current);
    setFlash(state);
    flashTimer.current = setTimeout(() => setFlash(null), ms);
  }, []);

  const mascot: MascotState = pending ? "thinking" : (flash ?? hold ?? "idle");

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || pending) return;
      const userMsg: ChatMessage = { id: uid("u"), role: "user", content };
      const history = [...messages.filter((m) => !m.error), userMsg].slice(-12);
      setMessages((prev) => [...prev, userMsg]);
      setPending(true);
      try {
        const reply = await ask({
          data: {
            role,
            messages: history.map((m) => ({ role: m.role, content: m.content })),
            ...(notes.length ? { recentNotes: notes.join("\n").slice(-3800) } : {}),
          },
        });
        if (reply.ok) {
          setMessages((prev) => [
            ...prev,
            { id: uid("a"), role: "assistant", content: reply.text, citations: reply.citations },
          ]);
          flashMascot("analytical", 2400);
        } else {
          setMessages((prev) => [
            ...prev,
            { id: uid("e"), role: "assistant", content: reply.error, error: true },
          ]);
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: uid("e"),
            role: "assistant",
            content: "ارتباط با دستیار قطع شد. دوباره تلاش کنید.",
            error: true,
          },
        ]);
      } finally {
        setPending(false);
      }
    },
    [ask, messages, notes, pending, role, flashMascot],
  );

  const openChat = useCallback(
    (prompt?: string) => {
      setChatOpen(true);
      if (prompt) void send(prompt);
    },
    [send],
  );

  const students = useMemo<StudentRow[]>(() => summary?.students ?? [], [summary]);

  const addObservation = useCallback(
    (studentId: number, obs: Observation) => {
      const student = students.find((s) => s.id === studentId);
      const kind = obs.kind === "alert" ? "alert" : obs.kind === "kudos" ? "kudos" : "milestone";
      setNotes((prev) => [
        ...prev,
        `- ${student?.name ?? "دانش‌آموز"} (${OBS_KIND_LABEL[obs.kind]}، ${obs.mentor}، ${formatPersianDate(obs.date)}): ${obs.text}`,
      ]);
      setLocalStream((prev) => [
        {
          id: uid("st"),
          kind,
          title: `${student?.name ?? "دانش‌آموز"} — ${OBS_KIND_LABEL[obs.kind]}`,
          body: obs.text,
          studentId,
          author: obs.mentor,
          time: "همین حالا",
          tag: student ? `پایه ${faNum(student.grade)}` : "—",
        },
        ...prev,
      ]);
      flashMascot("celebrate", 2800);
    },
    [students, flashMascot],
  );

  const stream = useMemo<StreamItem[]>(() => {
    const base = summary ? buildStream(summary) : [];
    return [...localStream, ...base];
  }, [summary, localStream]);

  const value = useMemo<DashboardContextValue>(
    () => ({
      mascot,
      flashMascot,
      setMascotHold,
      chatOpen,
      setChatOpen,
      openChat,
      messages,
      pending,
      role,
      setRole,
      send,
      clearChat: () => setMessages([]),
      summary,
      loading,
      error,
      me,
      students,
      stream,
      addObservation,
    }),
    [
      mascot,
      flashMascot,
      chatOpen,
      openChat,
      messages,
      pending,
      role,
      send,
      summary,
      loading,
      error,
      me,
      students,
      stream,
      addObservation,
    ],
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used inside DashboardProvider");
  return ctx;
}
