import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowLeft,
  Building2,
  ExternalLink,
  GraduationCap,
  Landmark,
  LogIn,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { apiMe, ApiError, type MeResponse } from "@/lib/api";
import { faNum } from "@/lib/dashboard";
import { fetchGlobalStats, type GlobalStats } from "@/lib/platform";

export const Route = createFileRoute("/platform")({
  head: () => ({
    meta: [
      { title: "مدیریت سامانه | آرمان‌نو - نسیم" },
      { name: "description", content: "گزارش اجرایی وزارت آموزش‌وپرورش و ابزارهای مدیریت سامانه" },
    ],
  }),
  component: PlatformAdminPage,
});

const QUICK_LINKS = [
  {
    href: "/admin/auth/user/add/",
    label: "ساخت کاربر",
    desc: "کاربران سامانه و مدیران مدرسه",
    Icon: UserPlus,
  },
  {
    href: "/admin/schools/school/add/",
    label: "ساخت مدرسه",
    desc: "فقط superuser",
    Icon: Building2,
  },
  { href: "/admin/auth/group/add/", label: "ساخت گروه نقش", desc: "گروه‌های دسترسی", Icon: Users },
  {
    href: "/admin/schools/schoolmodule/add/",
    label: "فعال‌سازی ماژول",
    desc: "مجوز ماژول‌های مدرسه",
    Icon: GraduationCap,
  },
  {
    href: "/admin/schools/schoolmembership/add/",
    label: "عضویت مدیر مدرسه",
    desc: "پیوند مدیر به مدرسه",
    Icon: ShieldCheck,
  },
];

function PlatformAdminPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [anonymous, setAnonymous] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const profile = await apiMe();
        if (cancelled) return;
        setMe(profile);
        if (!profile.is_platform_operator) {
          setError("این صفحه فقط برای مدیر سامانه (وزارت) در دسترس است.");
          return;
        }
        const next = await fetchGlobalStats();
        if (!cancelled) setStats(next);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          setAnonymous(true);
        } else {
          setError(err instanceof Error ? err.message : "دریافت گزارش ممکن نشد.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const denied =
    !loading && !anonymous && (error !== null || (me !== null && !me.is_platform_operator));

  return (
    <div className="min-h-screen">
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <a
          href="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground transition hover:text-primary-glow"
        >
          <ArrowLeft className="size-4" aria-hidden />
          بازگشت به داشبورد
        </a>

        <header className="mb-6">
          <p className="text-sm font-medium text-primary-glow">سکوی آرمان‌نو - نسیم</p>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-black">
            <Landmark className="size-7 text-primary-glow" aria-hidden />
            <span className="text-gradient">گزارش اجرایی وزارت آموزش‌وپرورش</span>
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            نمای کلی سامانه: مدارس، کاربران بر اساس نقش، و وضعیت فعال‌سازی ماژول‌ها.
          </p>
        </header>

        {loading && (
          <p className="rounded-2xl border border-border bg-surface/60 px-4 py-3 text-center text-sm text-muted-foreground">
            در حال دریافت گزارش…
          </p>
        )}

        {!loading && anonymous && (
          <section className="glass-strong rounded-[2rem] p-8 text-center">
            <LogIn className="mx-auto size-10 text-primary-glow" aria-hidden />
            <h2 className="mt-3 text-lg font-black">برای مشاهده گزارش وارد شوید</h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              این صفحه برای مدیر سامانه است. ابتدا وارد حساب کاربری خود شوید.
            </p>
            <a
              href="/login"
              className="mt-5 inline-flex items-center gap-2 rounded-full bg-gradient-primary px-5 py-2.5 font-bold text-primary-foreground shadow-glow transition hover:brightness-110"
            >
              ورود به سامانه
            </a>
          </section>
        )}

        {!loading && !anonymous && denied && (
          <section className="glass-strong rounded-[2rem] p-8 text-center">
            <ShieldCheck className="mx-auto size-10 text-warning" aria-hidden />
            <h2 className="mt-3 text-lg font-black">دسترسی مجاز نیست</h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              {error ?? "این صفحه فقط برای مدیر سامانه در دسترس است."}
            </p>
          </section>
        )}
        {!loading && !anonymous && !denied && stats && (
          <>
            <section className="grid gap-4 sm:grid-cols-2">
              <div className="glass-strong rounded-[2rem] p-6">
                <p className="text-sm text-muted-foreground">مدارس ثبت‌شده</p>
                <p className="mt-2 text-4xl font-black text-gradient">
                  {faNum(stats.schools_total)}
                </p>
              </div>
              <div className="glass-strong rounded-[2rem] p-6">
                <p className="text-sm text-muted-foreground">کاربران فعال</p>
                <p className="mt-2 text-4xl font-black text-gradient">{faNum(stats.users_total)}</p>
              </div>
            </section>

            <section className="mt-6 grid gap-6 lg:grid-cols-2">
              <div className="glass-strong rounded-[2rem] p-6">
                <h2 className="text-lg font-extrabold">کاربران بر اساس نقش</h2>
                <ul className="mt-4 space-y-2">
                  {stats.users_by_role.map((row) => (
                    <li
                      key={row.role}
                      className="flex items-center justify-between rounded-xl bg-surface/60 px-4 py-2.5"
                    >
                      <span className="text-sm font-semibold">{row.label}</span>
                      <span className="text-sm font-bold text-primary-glow">
                        {faNum(row.count)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="glass-strong rounded-[2rem] p-6">
                <h2 className="text-lg font-extrabold">ماژول‌های فعال</h2>
                <ul className="mt-4 space-y-2">
                  {stats.modules.map((m) => (
                    <li
                      key={m.key}
                      className="flex items-center justify-between rounded-xl bg-surface/60 px-4 py-2.5"
                    >
                      <span className="text-sm font-semibold">{m.label}</span>
                      <span className="text-sm text-muted-foreground">
                        {faNum(m.active_schools)} مدرسه
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="mt-6 glass-strong rounded-[2rem] p-6">
              <h2 className="text-lg font-extrabold">دسترسی سریع (پنل مدیریت Django)</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                این پیوندها به بخش مدیریت جنگو می‌روند تا کاربر، مدرسه و گروه بسازید.
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {QUICK_LINKS.map(({ href, label, desc, Icon }) => (
                  <a
                    key={href}
                    href={href}
                    className="group flex items-start gap-3 rounded-2xl border border-border bg-surface/60 p-4 transition-colors hover:border-primary/50 hover:bg-accent"
                  >
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-primary text-primary-foreground">
                      <Icon className="size-5" aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-sm font-bold">
                        {label}
                        <ExternalLink className="size-3 text-muted-foreground" aria-hidden />
                      </span>
                      <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                        {desc}
                      </span>
                    </span>
                  </a>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
