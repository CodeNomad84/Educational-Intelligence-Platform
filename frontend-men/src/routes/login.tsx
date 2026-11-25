import { createFileRoute } from "@tanstack/react-router";
import { KeyRound, LogIn, User } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { ApiError, apiLogin, apiMe } from "@/lib/api";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "ورود به سامانه | سکوی آموزشی-تربیتی آرمان نو" },
      {
        name: "description",
        content: "ورود به سامانه هوشمند رشد، مربیگری و انتخاب مأموریت‌محور",
      },
    ],
  }),
  component: LoginPage,
});

/** The post-login destination: `?next=` from Django's login_required, or the dashboard. */
function safeNext(): string {
  if (typeof window === "undefined") return "/";
  const raw = new URLSearchParams(window.location.search).get("next");
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Already signed in? Go straight to the dashboard instead of showing the form again.
    apiMe()
      .then(() => window.location.assign("/"))
      .catch(() => {});
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    if (!username.trim() || !password) {
      setError("نام کاربری و رمز عبور الزامی است.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await apiLogin(username.trim(), password);
      window.location.assign(safeNext());
    } catch (err) {
      if (err instanceof ApiError && err.mustChangePassword) {
        setError(
          "برای ورود ابتدا باید رمز عبور خود را تغییر دهید. لطفاً با مدیر سامانه تماس بگیرید.",
        );
      } else {
        setError(err instanceof Error ? err.message : "ورود ناموفق بود. دوباره تلاش کنید.");
      }
      setPending(false);
    }
  }

  return (
    <div className="min-h-screen grid-bg">
      <div className="hero-bg min-h-screen">
        <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
          <div className="glass glow-primary relative overflow-hidden p-8">
            <a
              href="/"
              className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground transition hover:text-primary"
            >
              بازگشت به داشبورد
            </a>

            <div className="mb-6">
              <h1 className="text-2xl font-extrabold">
                ورود به <span className="text-primary">سامانه</span>
              </h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                برای مشاهده داشبورد رشد، مربیگری و انتخاب مأموریت‌محور وارد حساب کاربری خود شوید.
              </p>
            </div>

            <form onSubmit={onSubmit} className="space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">نام کاربری</span>
                <div className="flex items-center gap-2 rounded-xl border border-border bg-background/70 px-3 transition focus-within:border-primary">
                  <User className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <input
                    autoComplete="username"
                    dir="ltr"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full bg-transparent py-3 text-start outline-none placeholder:text-muted-foreground"
                    placeholder="username"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">رمز عبور</span>
                <div className="flex items-center gap-2 rounded-xl border border-border bg-background/70 px-3 transition focus-within:border-primary">
                  <KeyRound className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <input
                    type="password"
                    autoComplete="current-password"
                    dir="ltr"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-transparent py-3 text-start outline-none placeholder:text-muted-foreground"
                    placeholder="••••••••"
                  />
                </div>
              </label>

              {error && (
                <p
                  role="alert"
                  className="rounded-xl border border-gold/40 bg-gold/10 px-3 py-2 text-sm leading-6 text-gold"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={pending}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-bold text-primary-foreground transition hover:brightness-110 disabled:opacity-60"
              >
                <LogIn className="size-5" aria-hidden />
                {pending ? "در حال ورود…" : "ورود به سامانه"}
              </button>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
