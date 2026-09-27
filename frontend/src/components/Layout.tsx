import {
  Activity,
  BarChart3,
  CloudRain,
  Info,
  LifeBuoy,
  MapPin,
  Menu,
  Radio,
  ShieldAlert,
  UserCog,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { LANGS } from "../i18n";
import { useLive } from "../state/live";
import { useSession } from "../state/session";
import { LevelBadge } from "./ui";

const PUBLIC_NAV: { to: string; labelKey: string; Icon: typeof MapPin; end?: boolean }[] = [
  { to: "/", labelKey: "nav.home", Icon: MapPin, end: true },
  { to: "/report", labelKey: "nav.report", Icon: ShieldAlert },
  { to: "/shelters", labelKey: "nav.shelters", Icon: LifeBuoy },
  { to: "/roads", labelKey: "nav.roads", Icon: CloudRain },
  { to: "/model", labelKey: "nav.model", Icon: Info },
];

const STAFF_NAV: { to: string; labelKey: string; Icon: typeof MapPin; end?: boolean }[] = [
  { to: "/responder", labelKey: "nav.responder", Icon: UserCog },
  { to: "/console", labelKey: "nav.admin", Icon: BarChart3 },
];

export function Layout({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const { status, updates } = useLive();
  const { user, isStaff, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  const items = [...PUBLIC_NAV, ...(isStaff ? STAFF_NAV : [])];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-50 bg-ink-950 text-white">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-3 h-14">
            <Link to="/" className="flex items-center gap-2.5 shrink-0 group">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-risk-red to-risk-orange grid place-items-center shrink-0 shadow-lg shadow-risk-red/25">
                <Activity size={17} strokeWidth={2.6} />
              </span>
              <span className="leading-none">
                <span className="block text-[15px] font-extrabold tracking-tight group-hover:opacity-90">
                  {t("brand.name")}
                </span>
                <span className="block text-[9px] font-semibold uppercase tracking-[0.16em] text-ink-400 mt-0.5">
                  Uttarakhand ward watch
                </span>
              </span>
            </Link>

            <nav className="hidden lg:flex items-center gap-0.5 ml-4 flex-1 min-w-0">
              {items.map(({ to, labelKey, Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors whitespace-nowrap ${
                      isActive ? "bg-white/12 text-white" : "text-ink-300 hover:bg-white/6 hover:text-white"
                    }`
                  }
                >
                  <Icon size={14} strokeWidth={2.2} />
                  {t(labelKey)}
                </NavLink>
              ))}
            </nav>

            <div className="flex items-center gap-2 ml-auto">
              <LiveDot status={status} updates={updates} />

              <div className="hidden sm:flex items-center rounded-lg bg-white/8 p-0.5">
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    onClick={() => i18n.changeLanguage(l.code)}
                    className={`px-2 py-1 rounded-md text-[11px] font-bold transition-colors ${
                      i18n.language === l.code ? "bg-white text-ink-900" : "text-ink-300 hover:text-white"
                    }`}
                    title={l.label}
                  >
                    {l.native}
                  </button>
                ))}
              </div>

              {user ? (
                <div className="hidden md:flex items-center gap-2 pl-2 ml-1 border-l border-white/12">
                  <div className="text-right leading-tight">
                    <span className="block text-[12px] font-semibold max-w-[9rem] truncate">
                      {user.full_name}
                    </span>
                    <span className="block text-[9px] uppercase tracking-widest text-ink-400 font-bold">
                      {user.role.replace("_", " ")}
                    </span>
                  </div>
                  <button onClick={signOut} className="btn btn-sm bg-white/10 hover:bg-white/18 text-white">
                    {t("nav.signOut")}
                  </button>
                </div>
              ) : (
                <Link to="/signin" className="btn btn-sm bg-white/10 hover:bg-white/18 text-white hidden sm:inline-flex">
                  {t("nav.signIn")}
                </Link>
              )}

              <button
                className="lg:hidden w-9 h-9 grid place-items-center rounded-lg bg-white/10"
                onClick={() => setOpen((v) => !v)}
                aria-label="Menu"
              >
                {open ? <X size={17} /> : <Menu size={17} />}
              </button>
            </div>
          </div>
        </div>

        {open && (
          <div className="lg:hidden border-t border-white/10 bg-ink-900 animate-slide">
            <div className="px-4 py-3 grid gap-1">
              {items.map(({ to, labelKey, Icon }) => (
                <Link
                  key={to}
                  to={to}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium text-ink-200 hover:bg-white/8"
                >
                  <Icon size={15} />
                  {t(labelKey)}
                </Link>
              ))}
              <div className="flex items-center gap-2 pt-2 mt-1 border-t border-white/10">
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    onClick={() => i18n.changeLanguage(l.code)}
                    className={`px-2.5 py-1.5 rounded-lg text-xs font-bold ${
                      i18n.language === l.code ? "bg-white text-ink-900" : "bg-white/10 text-ink-300"
                    }`}
                  >
                    {l.native}
                  </button>
                ))}
                {user ? (
                  <button onClick={() => { setOpen(false); signOut(); }} className="btn btn-sm bg-white/10 text-white ml-auto">
                    {t("nav.signOut")}
                  </button>
                ) : (
                  <Link to="/signin" onClick={() => setOpen(false)} className="btn btn-sm bg-white/10 text-white ml-auto">
                    {t("nav.signIn")}
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 w-full max-w-[1400px] mx-auto px-4 sm:px-6 py-5 sm:py-7">{children}</main>

      <footer className="border-t border-[var(--line)] bg-white mt-8">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 grid gap-4 sm:grid-cols-[1fr_auto] items-start">
          <div>
            <p className="text-[13px] font-bold text-ink-900">
              {t("brand.name")} · {t("brand.tagline")}
            </p>
            <p className="text-[11px] text-ink-400 mt-1.5 leading-relaxed max-w-2xl">
              Susceptibility scores are a decision-support prior built from rainfall, terrain and
              corroborated resident reports — <strong>not</strong> a prediction that a particular slope
              will fail. Seed terrain and population figures are realistic approximations for
              demonstration, not surveyed data. Built for Elite Coders CodeSprint 2026 and released under
              the MIT licence.
            </p>
            <p className="text-[11px] text-ink-400 mt-1.5">
              Map data ©{" "}
              <a href="https://www.openstreetmap.org/copyright" className="underline" target="_blank" rel="noreferrer">
                OpenStreetMap
              </a>{" "}
              contributors · rainfall nowcast by Open-Meteo when live mode is on
              {location.pathname === "/model" ? " · full methodology on this page" : ""}
            </p>
          </div>
          <div className="flex flex-col items-start sm:items-end gap-2">
            <div className="pill !border-risk-red/30 !bg-risk-red/5 !text-risk-red font-bold">
              <PhoneIcon /> {t("hero.emergency")}: 1070 · 112
            </div>
            <Link to="/model" className="text-[11px] text-ink-400 hover:text-ink-700 underline underline-offset-2">
              Read the model limits before relying on a score
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function LiveDot({ status, updates }: { status: string; updates: number }) {
  const tone = status === "open" ? "#22c55e" : status === "connecting" ? "#eab308" : "#94a3b8";
  return (
    <span
      className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-white/8 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-ink-300"
      title={`${updates} live updates since this page opened`}
    >
      <Radio size={11} color={tone} />
      <span style={{ color: tone }}>{status === "open" ? "live" : status}</span>
    </span>
  );
}

function PhoneIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

export function PageHeader({
  eyebrow,
  title,
  sub,
  actions,
  level,
}: {
  eyebrow?: string;
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  level?: Parameters<typeof LevelBadge>[0]["level"];
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="text-xl sm:text-2xl mt-1 flex items-center gap-3 flex-wrap">
          {title}
          {level && <LevelBadge level={level} size="md" />}
        </h1>
        {sub && <p className="text-[13px] text-ink-400 mt-1.5 max-w-2xl leading-relaxed">{sub}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}
