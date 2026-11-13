import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useServerFn } from "@tanstack/react-start";

import { STREAM, STUDENTS, type Observation, type StreamItem, type Student } from "@/data/school";
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

  students: Student[];
  stream: StreamItem[];
  addObservation: (studentId: string, obs: Observation) => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

let idCounter = 0;
const uid = (p: string) => `${p}-${Date.now().toString(36)}-${(idCounter++).toString(36)}`;

export function DashboardProvider({ children }: { children: ReactNode }) {
  const ask = useServerFn(askMentor);

  const [flash, setFlash] = useState<MascotState | null>(null);
  const [hold, setMascotHold] = useState<MascotState | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [role, setRole] = useState<MentorRole>("teacher");

  const [students, setStudents] = useState<Student[]>(STUDENTS);
  const [stream, setStream] = useState<StreamItem[]>(STREAM);
  const [notes, setNotes] = useState<string[]>([]);

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
          setMessages((prev) => [...prev, { id: uid("e"), role: "assistant", content: reply.error, error: true }]);
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          { id: uid("e"), role: "assistant", content: "ارتباط با دستیار قطع شد. دوباره تلاش کنید.", error: true },
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

  const addObservation = useCallback(
    (studentId: string, obs: Observation) => {
      setStudents((prev) =>
        prev.map((s) => (s.id === studentId ? { ...s, observations: [obs, ...s.observations] } : s)),
      );
      const student = students.find((s) => s.id === studentId);
      if (!student) return;
      const kindLabel = obs.kind === "kudos" ? "تشویق" : obs.kind === "alert" ? "هشدار" : "پیشنهاد رشد";
      setNotes((prev) => [...prev, `- ${student.name} (${kindLabel}، ${obs.mentor}، ${obs.date}): ${obs.text}`]);
      setStream((prev) => [
        {
          id: uid("st"),
          kind: obs.kind === "alert" ? "alert" : obs.kind === "kudos" ? "kudos" : "milestone",
          title: `${kindLabel} تازه برای ${student.name}`,
          body: obs.text,
          studentId,
          author: obs.mentor,
          time: "همین حالا",
          tag: student.track,
        },
        ...prev,
      ]);
      flashMascot("celebrate", 2800);
    },
    [students, flashMascot],
  );

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
      students,
      stream,
      addObservation,
    }),
    [mascot, flashMascot, chatOpen, openChat, messages, pending, role, send, students, stream, addObservation],
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used inside DashboardProvider");
  return ctx;
}
