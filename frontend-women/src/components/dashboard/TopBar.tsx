import { Bell, LogIn, ShieldCheck, Sprout } from "lucide-react";

import { useDashboard } from "./dashboard-context";

const ROLE_LABELS: Record<string, string> = {
  SchoolAdmin: "مدیر مدرسه",
  Teacher: "معلم",
  GradeLead: "مربی پایه",
  Counselor: "مشاور",
  Parent: "والدین",
  Student: "دانش‌آموز",
};

const NAV = [
  { href: "#pulse", label: "نبض مدرسه" },
  { href: "#radar", label: "رادار شایستگی" },
  { href: "#stream", label: "تابلوی رشد" },
  { href: "#roster", label: "متربیان" },
];

export function TopBar() {
  const { me, loading } = useDashboard();
  const displayName = me?.display_name ?? "کاربر";
  const roleLabel = me?.role
    ? (ROLE_LABELS[me.role] ?? "سکوی آموزشی-تربیتی")
    : "سکوی آموزشی-تربیتی";
  const unauthenticated = !loading && !me;
  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <a href="#top" className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-gradient-primary shadow-glow">
            <Sprout className="size-5 text-primary-foreground" aria-hidden />
          </span>
          <span className="leading-tight">
            <span className="block text-base font-extrabold tracking-tight">آرمان‌نو - نسیم</span>
            <span className="hidden text-xs text-muted-foreground sm:block">
              سکوی آموزشی-تربیتی
            </span>
          </span>
        </a>

        <nav
          aria-label="بخش‌های داشبورد"
          className="mx-auto hidden items-center gap-1 rounded-full border border-border bg-surface/60 p-1 md:flex"
        >
          {NAV.map((n) => (
            <a
              key={n.href}
              href={n.href}
              className="rounded-full px-4 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              {n.label}
            </a>
          ))}
        </nav>

        <div className="ms-auto flex items-center gap-2 md:ms-0">
          {me?.is_platform_operator && (
            <a
              href="/platform"
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-accent"
            >
              <ShieldCheck className="size-4" aria-hidden />
              مدیریت سامانه
            </a>
          )}
          <button
            type="button"
            aria-label="اعلان‌ها"
            className="relative grid size-10 place-items-center rounded-full border border-border bg-surface/60 text-muted-foreground transition-colors hover:text-foreground"
          >
            <Bell className="size-[18px]" />
            <span className="absolute end-2 top-2 size-2 rounded-full bg-warning ring-2 ring-background" />
          </button>
          {unauthenticated ? (
            <a
              href="/login"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-primary px-4 py-2 text-sm font-bold text-primary-foreground shadow-glow transition hover:brightness-110"
            >
              <LogIn className="size-4" aria-hidden />
              ورود به سامانه
            </a>
          ) : loading ? null : (
            <div className="flex items-center gap-2 rounded-full border border-border bg-surface/60 py-1 pe-1 ps-3">
              <span className="hidden text-end leading-tight sm:block">
                <span className="block text-sm font-semibold">{displayName}</span>
                <span className="block text-[11px] text-muted-foreground">{roleLabel}</span>
              </span>
              <span className="grid size-8 place-items-center rounded-full bg-gradient-growth text-sm font-bold text-success-foreground">
                {displayName.charAt(0)}
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
