/**
 * «رهنما» — mentor assistant client. The real model lives behind Django's JSON endpoints
 * (`GET /api/ai/status/`, `POST /api/ai/chat/`); this module only types and calls them.
 *
 * Roles are read from `MeResponse.roles` (Django group names). The server re-checks the requested
 * persona against the caller's real roles, so the tabs here are a UI convenience, never an auth check.
 */
import { apiFetch } from "./api";

export type MentorRole = "teacher" | "counselor" | "principal";

export interface MentorRoleMeta {
  id: MentorRole;
  label: string;
  /** Django role group names (students/access.py) that grant this persona. */
  roles: string[];
}

export const MENTOR_ROLES: MentorRoleMeta[] = [
  { id: "teacher", label: "معلم", roles: ["Teacher", "GradeLead"] },
  { id: "counselor", label: "مشاور", roles: ["Counselor"] },
  { id: "principal", label: "مدیر", roles: ["SchoolAdmin"] },
];

export function mentorRolesFor(roles: string[]): MentorRole[] {
  const held = new Set(roles ?? []);
  return MENTOR_ROLES.filter((role) => role.roles.some((name) => held.has(name))).map(
    (role) => role.id,
  );
}

export type AiStatusReason =
  "no_role" | "ai_disabled" | "module_locked" | "key_not_set" | "service_unavailable";

export interface AiStatus {
  enabled: boolean;
  reason: AiStatusReason | null;
  detail: string | null;
  roles: MentorRole[];
}

export interface AiChatReply {
  text: string;
  label: string;
  provider_class: string;
}

/** `GET /api/ai/status/` — whether the mentor assistant is usable for the signed-in user. */
export function fetchAiStatus(): Promise<AiStatus> {
  return apiFetch<AiStatus>("/ai/status/");
}

/** `POST /api/ai/chat/` — one mentor chat turn. The server checks `role` against the real roles. */
export function askMentor(
  role: MentorRole,
  messages: { role: "user" | "assistant"; content: string }[],
): Promise<AiChatReply> {
  return apiFetch<AiChatReply>("/ai/chat/", {
    method: "POST",
    body: JSON.stringify({ role, messages }),
  });
}
