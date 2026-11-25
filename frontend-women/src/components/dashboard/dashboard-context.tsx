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

import { apiMe, ApiError, type MeResponse } from "@/lib/api";
import {
  buildStream,
  faNum,
  fetchDashboardSummary,
  type DashboardSummary,
  type Observation,
  type StreamItem,
  type StudentRow,
} from "@/lib/dashboard";
import {
  askMentor,
  fetchAiStatus,
  mentorRolesFor,
  type AiStatus,
  type MentorRole,
} from "@/lib/mentor-chat";

export type MascotState = "idle" | "thinking" | "analytical" | "celebrate";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
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
  aiStatus: AiStatus | null;
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
  const [flash, setFlash] = useState<MascotState | null>(null);
  const [hold, setMascotHold] = useState<MascotState | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [role, setRole] = useState<MentorRole>("teacher");

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const statusLoaded = useRef(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<StreamItem[]>([]);

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
        if (err instanceof ApiError && err.status === 401) {
          // Anonymous visitor: keep the landing visible (me stays null) with a login
          // entry in the top bar instead of a hard redirect (ADR-0014 Phase 3 login UI).
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

  const availableRoles = useMemo<MentorRole[]>(() => (me ? mentorRolesFor(me.roles) : []), [me]);

  // Keep the selected persona inside what the account actually holds.
  useEffect(() => {
    const first = availableRoles[0];
    if (first && !availableRoles.includes(role)) {
      setRole(first);
    }
  }, [availableRoles, role]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || pending || (aiStatus !== null && !aiStatus.enabled)) return;
      const userMsg: ChatMessage = { id: uid("u"), role: "user", content };
      const history = [...messages.filter((m) => !m.error), userMsg].slice(-12);
      setMessages((prev) => [...prev, userMsg]);
      setPending(true);
      try {
        const reply = await askMentor(
          role,
          history.map((m) => ({ role: m.role, content: m.content })),
        );
        setMessages((prev) => [...prev, { id: uid("a"), role: "assistant", content: reply.text }]);
        flashMascot("analytical", 2400);
      } catch (err) {
        const content2 =
          err instanceof ApiError && err.message
            ? err.message
            : "ارتباط با دستیار قطع شد. دوباره تلاش کنید.";
        setMessages((prev) => [
          ...prev,
          { id: uid("e"), role: "assistant", content: content2, error: true },
        ]);
      } finally {
        setPending(false);
      }
    },
    [messages, pending, role, flashMascot, aiStatus],
  );

  const openChat = useCallback(
    (prompt?: string) => {
      setChatOpen(true);
      const load: Promise<AiStatus> =
        statusLoaded.current && aiStatus
          ? Promise.resolve(aiStatus)
          : fetchAiStatus()
              .then((status) => {
                setAiStatus(status);
                return status;
              })
              .catch((): AiStatus => {
                const fallback: AiStatus = {
                  enabled: false,
                  reason: "service_unavailable",
                  detail: "سرویس هوش مصنوعی در دسترس نیست.",
                  roles: availableRoles,
                };
                setAiStatus(fallback);
                return fallback;
              });
      void load.then((status) => {
        statusLoaded.current = true;
        if (prompt && status.enabled) void send(prompt);
      });
    },
    [send, aiStatus, availableRoles],
  );

  const students = useMemo<StudentRow[]>(() => summary?.students ?? [], [summary]);

  const addObservation = useCallback(
    (studentId: number, obs: Observation) => {
      const student = students.find((s) => s.id === studentId);
      const kind = obs.kind === "alert" ? "alert" : obs.kind === "kudos" ? "kudos" : "milestone";
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
      aiStatus,
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
      aiStatus,
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
