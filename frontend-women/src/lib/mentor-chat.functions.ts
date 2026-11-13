import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

import { KNOWLEDGE_BASE, type KnowledgeDoc } from "@/data/school";

/**
 * «رهنما» — the school mentor assistant.
 *
 * ADR-0008 / docs/AI_GOVERNANCE.md (owner decision D9, docs/changes/0040): NO external model may receive school data.
 * The previous implementation imported `@lovable.dev/ai-gateway` and sent ``rosterDigest()`` (student growth data) plus
 * the caller's counseling notes to a third-party gateway. That call is removed: this module now answers **extractively**
 * from the built-in school knowledge base only, on the server, and never leaves the process. No student record and no
 * counselor note is placed in a prompt, and nothing is sent anywhere.
 *
 * When an approved in-house model path exists (Django → FastAPI, ADR-0002), it replaces ``composeLocalAnswer`` behind
 * this same ``askMentor`` signature; the UI does not change.
 */
const ROLE_PERSONA = {
  teacher:
    "کاربر یک «معلم» است. روی راهکارهای کلاسی عملی، تمرین‌های بازی‌وار، تقسیم‌بندی گروه‌ها و بازخورد روزانه تمرکز کن.",
  counselor:
    "کاربر یک «مشاور» است. روی ریشه‌یابی رفتاری و انگیزشی، سطح مداخله، گفت‌وگو با خانواده و برنامه رشد انفرادی تمرکز کن.",
  principal:
    "کاربر «مدیر» مدرسه است. روی تصویر کلان، شاخص‌ها، اولویت‌بندی منابع، تصمیم‌های اجرایی و گزارش‌دهی تمرکز کن.",
} as const;

export type MentorRole = keyof typeof ROLE_PERSONA;

const InputSchema = z.object({
  role: z.enum(["teacher", "counselor", "principal"]),
  messages: z
    .array(z.object({ role: z.enum(["user", "assistant"]), content: z.string().min(1).max(8000) }))
    .min(1)
    .max(24),
  recentNotes: z.string().max(4000).optional(),
});

export interface Citation {
  index: number;
  title: string;
  source: string;
  snippet: string;
}

export type MentorReply =
  | { ok: true; text: string; citations: Citation[] }
  | { ok: false; error: string };

function tokenize(text: string): string[] {
  return text
    .replace(/[\u200c]/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 3);
}

/** Lightweight lexical retrieval over the school knowledge base. */
function retrieve(query: string, k = 3): KnowledgeDoc[] {
  const q = new Set(tokenize(query));
  const scored = KNOWLEDGE_BASE.map((doc) => {
    const tokens = tokenize(`${doc.title} ${doc.content}`);
    let score = 0;
    for (const t of tokens) if (q.has(t)) score += 1;
    for (const t of q) if (doc.title.includes(t)) score += 3;
    return { doc, score };
  }).sort((a, b) => b.score - a.score);
  const picked = scored.filter((s) => s.score > 0).slice(0, k).map((s) => s.doc);
  if (picked.length === 0) return KNOWLEDGE_BASE.filter((d) => d.id === "kb-framework" || d.id === "kb-weekly");
  return picked;
}

/** Up to `limit` document lines that share vocabulary with the question; ties keep document order. */
function relevantLines(query: string, docs: KnowledgeDoc[], limit = 4): { line: string; docIndex: number }[] {
  const words = new Set(tokenize(query));
  const rows: { line: string; score: number; docIndex: number; order: number }[] = [];
  docs.forEach((doc, docIndex) => {
    const lines = doc.content
      .split(/[\n.؛!؟]+/u)
      .map((part) => part.trim())
      .filter((part) => part.length >= 12);
    lines.forEach((line, lineIndex) => {
      let score = 0;
      for (const token of tokenize(line)) if (words.has(token)) score += 1;
      rows.push({ line, score, docIndex, order: docIndex * 1000 + lineIndex });
    });
  });
  const matched = rows
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.order - b.order)
    .slice(0, limit);
  const chosen = matched.length > 0 ? matched : rows.slice(0, 2);
  return chosen.map((row) => ({ line: row.line, docIndex: row.docIndex }));
}

/**
 * A deterministic, extractive answer built only from the retrieved school documents. No model, no network, no student
 * data: the same question always produces the same answer, and every bullet carries a document number.
 */
function composeLocalAnswer(role: MentorRole, docs: KnowledgeDoc[], query: string): string {
  const lines = relevantLines(query, docs);
  if (lines.length === 0) return "";
  return [
    "### جمع‌بندی",
    "پاسخ زیر بر پایهٔ اسناد داخلی مدرسه و به‌صورت استخراجی تهیه شده است (بدون ارسال داده به سرویس بیرونی).",
    ROLE_PERSONA[role],
    "",
    "### نکات مرتبط",
    ...lines.map((row) => `- ${row.line} [${row.docIndex + 1}]`),
    "",
    "### گام بعدی پیشنهادی",
    "- پرسش را با نام شاخص، پایه یا بازهٔ زمانی دقیق‌تر بپرسید تا سند مرتبط‌تری انتخاب شود.",
    "- برای هر نکته، شمارهٔ منبع داخل کروشه را با فهرست منابع پایین پاسخ تطبیق دهید.",
  ].join("\n");
}

export const askMentor = createServerFn({ method: "POST" })
  .inputValidator((data: unknown) => InputSchema.parse(data))
  .handler(({ data }): MentorReply => {
    const lastUser = [...data.messages].reverse().find((message) => message.role === "user")?.content ?? "";
    const docs = retrieve(lastUser);
    const text = composeLocalAnswer(data.role, docs, lastUser);
    if (!text) {
      return { ok: false, error: "برای این پرسش سندی در پایگاه دانش مدرسه پیدا نشد؛ پرسش را دقیق‌تر بپرسید." };
    }
    const citations: Citation[] = docs.map((doc, index) => ({
      index: index + 1,
      title: doc.title,
      source: doc.source,
      snippet: doc.content.slice(0, 180) + "…",
    }));
    return { ok: true, text, citations };
  });
