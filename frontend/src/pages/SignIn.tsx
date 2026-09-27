import { KeyRound, LogIn, ShieldCheck, User } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ErrorState } from "../components/ui";
import { PageHeader } from "../components/Layout";
import { useSession } from "../state/session";

const DEMOS = [
  { role: "District admin", who: "Dr Meera Rawat", id: "collector.demo@aapaatsathi.in", why: "Issue and broadcast warnings, retune the model, prove delivery" },
  { role: "Field responder", who: "Arun Negi", id: "field.demo@aapaatsathi.in", why: "Verify resident reports, close roads, update shelter occupancy" },
  { role: "Citizen", who: "Suresh Adhikari", id: "citizen.demo@aapaatsathi.in", why: "Ranikhot resident subscribed to Garhwali SMS warnings" },
  { role: "System admin", who: "Platform owner", id: "admin.demo@aapaatsathi.in", why: "Full console including the audit trail" },
];
const PASSWORD = "Aapaat@2026";

export default function SignIn() {
  const { signIn } = useSession();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!identifier || !password) {
      setError("Enter your email or phone, and your password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(identifier.trim(), password);
      const to = (location.state as { from?: string } | null)?.from ?? "/console";
      navigate(to, { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const quickFill = (id: string) => {
    setIdentifier(id);
    setPassword(PASSWORD);
    setError(null);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader
        eyebrow="Staff access"
        title={t("nav.signIn")}
        sub="Citizens do not need an account to file a hazard report or read ward risk — this page is only for field teams and the district control room."
      />

      <div className="grid lg:grid-cols-2 gap-5 items-start">
        <form onSubmit={submit} className="panel p-5 sm:p-6">
          <label className="label" htmlFor="id">
            Email or phone
          </label>
          <div className="relative">
            <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
            <input
              id="id"
              className="input !pl-9"
              autoComplete="username"
              placeholder="collector.demo@aapaatsathi.in"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
            />
          </div>

          <label className="label mt-4" htmlFor="pw">
            Password
          </label>
          <div className="relative">
            <KeyRound size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
            <input
              id="pw"
              type="password"
              className="input !pl-9"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <div className="mt-4">
              <ErrorState error={error} compact />
            </div>
          )}

          <button className="btn-primary w-full mt-5" disabled={busy} type="submit">
            <LogIn size={15} /> {busy ? "Signing in…" : t("nav.signIn")}
          </button>

          <p className="text-[11px] text-ink-400 mt-3 leading-relaxed">
            Passwords are stored with bcrypt (SHA-256 pre-hashed so long passphrases work). Sessions use short-lived
            JWTs with a refresh token, and every broadcast, verdict and model change is written to the audit trail
            against your account.
          </p>
        </form>

        <div className="grid gap-3">
          <p className="eyebrow flex items-center gap-1.5">
            <ShieldCheck size={12} /> Demo accounts · password {PASSWORD}
          </p>
          {DEMOS.map((d) => (
            <button
              key={d.id}
              onClick={() => quickFill(d.id)}
              className={`text-left panel-tight p-3.5 hover:border-risk-blue hover:shadow-md transition-all ${
                identifier === d.id ? "border-risk-blue ring-2 ring-risk-blue/20" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-[13px] font-bold text-ink-900">{d.role}</p>
                <span className="chip bg-ink-100 text-ink-600">{d.who}</span>
              </div>
              <p className="text-[11px] text-ink-500 font-mono mt-1 break-all">{d.id}</p>
              <p className="text-[11px] text-ink-400 mt-1.5 leading-snug">{d.why}</p>
            </button>
          ))}
          <p className="text-[11px] text-ink-400 leading-relaxed">
            Click one to fill the form, then sign in. Roles are enforced server-side: a citizen token cannot issue a
            warning, and a field responder cannot retune the model.
          </p>
        </div>
      </div>
    </div>
  );
}
