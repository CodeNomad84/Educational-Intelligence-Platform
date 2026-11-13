/**
 * The single HTTP client for the Django API (ADR-0014, docs/changes/0040 §18.1).
 *
 * * `VITE_API_URL` (default `/api`) — in dev the Vite server proxies `/api` to Django, so the app is same-origin and
 *   the session cookie is simply the browser's.
 * * `credentials: "include"` — the Django session cookie travels with every call, including cross-origin calls to an
 *   explicitly allowlisted origin (`CORS_ALLOW_CREDENTIALS`, `docs/SECURITY.md`).
 * * `X-CSRFToken` — read from the `csrftoken` cookie; Django's CsrfViewMiddleware refuses a POST without it, so a
 *   mutating call fetches the cookie from `GET /api/auth/csrf/` first when it is missing.
 *
 * No token is ever stored in localStorage: the server-side session is the credential.
 */
// Bracket access because tsconfig sets `noPropertyAccessFromIndexSignature` (D6 typecheck gate, 0042).
const BASE_URL: string = import.meta.env["VITE_API_URL"] || "/api";
const CSRF_COOKIE = "csrftoken";
const CSRF_HEADER = "X-CSRFToken";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

export interface SchoolRef {
  id: number;
  name: string;
}

/** `GET /api/auth/me/` — the contract in docs/changes/0040 §4.3. Nothing private (national id, phone, notes) is here. */
export interface MeResponse {
  id: number;
  username: string;
  display_name: string;
  roles: string[];
  role: string | null;
  schools: SchoolRef[];
  school: SchoolRef | null;
  modules: string[];
  is_platform_operator: boolean;
  must_change_password: boolean;
  gender_scope: string | null;
  theme: string | null;
}

/** `403` body of `POST /api/auth/login/` when the account must choose a new password first. */
export interface PasswordChangeRequired {
  detail: string;
  code: "password_change_required";
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : "";
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  /** A login the account may not complete until it has changed its password. */
  get mustChangePassword(): boolean {
    return (
      this.status === 403 &&
      this.body !== null &&
      typeof this.body === "object" &&
      (this.body as { code?: unknown }).code === "password_change_required"
    );
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null; // server render: there is no cookie jar here
  const match = new RegExp(`(?:^|; )${name}=([^;]*)`).exec(document.cookie);
  const value = match?.[1];
  return value ? decodeURIComponent(value) : null;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

let pendingCsrf: Promise<string> | null = null;

async function requestCsrf(): Promise<string> {
  const response = await fetch(`${BASE_URL}/auth/csrf/`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new ApiError(response.status, await parseBody(response));
  const body = (await response.json()) as { csrfToken?: string };
  return body.csrfToken ?? readCookie(CSRF_COOKIE) ?? "";
}

/** The CSRF token for a mutating call: from the cookie, or fetched once from `GET /api/auth/csrf/`. */
export async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  if (pendingCsrf === null) {
    pendingCsrf = requestCsrf().finally(() => {
      pendingCsrf = null;
    });
  }
  const token = await pendingCsrf;
  return token;
}

/** One call to the API: JSON in, JSON out, session cookie and CSRF header handled. Throws `ApiError` on a non-2xx. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (!SAFE_METHODS.has(method)) headers.set(CSRF_HEADER, await csrfToken());
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  const body = await parseBody(response);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

/** `POST /api/auth/login/` — on success the session cookie is set and the profile is returned. */
export function apiLogin(username: string, password: string): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** `POST /api/auth/logout/` — ends the session server-side. */
export async function apiLogout(): Promise<void> {
  await apiFetch<null>("/auth/logout/", { method: "POST" });
}

/** `GET /api/auth/me/` — the signed-in account; an anonymous caller gets `ApiError` with status 401. */
export function apiMe(schoolId?: number): Promise<MeResponse> {
  return apiFetch<MeResponse>(
    schoolId === undefined ? "/auth/me/" : `/auth/me/?school=${schoolId}`,
  );
}
