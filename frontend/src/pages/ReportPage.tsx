import { Camera, CheckCircle2, Crosshair, ImageOff, MapPin, Send, ShieldAlert, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { WardRiskSummary } from "../api/types";
import { Card, ErrorState, LEVEL_COLOR, Loading, useToast } from "../components/ui";
import { RiskMap } from "../components/RiskMap";
import { useAsync, useGeolocate } from "../hooks";
import { useSession } from "../state/session";

const HAZARDS = [
  { key: "landslide", en: "Landslide or soil movement", hi: "भूस्खलन / मिट्टी खिसकना", gar: "डंडगिरी / माटो खिसकना" },
  { key: "flash_flood", en: "Flash flooding", hi: "अचानक बाढ़", gar: "अचानक बाढ़" },
  { key: "road_block", en: "Road blocked", hi: "रास्ता बंद", gar: "रास्ता बंद" },
  { key: "debris_flow", en: "Debris or mud flow", hi: "मलबा / कीचड़", gar: "मलबा प्रवाह" },
  { key: "cloudburst", en: "Cloudburst / extreme rain", hi: "क्लाउडबर्स्ट", gar: "मेला पड़ना" },
  { key: "water_logging", en: "Waterlogging", hi: "जलभराव", gar: "पानी भरना" },
  { key: "earthquake", en: "Earthquake damage", hi: "भूकंप क्षति", gar: "भूकंप क्षति" },
  { key: "glacial_lake", en: "Glacial lake swelling", hi: "हिमनदीय झील", gar: "हिमनद झील" },
] as const;

const SEVERITY = ["Barely noticeable", "Minor", "Notable", "Serious", "Dangerous right now"];

export default function ReportPage() {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const { user } = useSession();
  const { coords, status: geoStatus, locate } = useGeolocate();
  const overview = useAsync(() => api.overview(), []);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const wards: WardRiskSummary[] = overview.data?.wards ?? [];
  const [hazard, setHazard] = useState<string>("landslide");
  const [severity, setSeverity] = useState(4);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ code: string; message: string; merged: boolean; confidence: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const position = pin ?? coords ?? null;
  const drop = (list: WardRiskSummary[], lat: number, lng: number) =>
    list.reduce<{ w: WardRiskSummary; d: number } | null>((best, w) => {
      const d = dist(lat, lng, w.latitude, w.longitude);
      return !best || d < best.d ? { w, d } : best;
    }, null);
  const matched = position ? drop(wards, position.lat, position.lng) : null;

  const submit = async () => {
    setError(null);
    if (!position) return setError("Allow location access, or tap the map to place the hazard.");
    if (!consent) return setError("Please confirm you are happy for this to reach the control room.");
    if (!description.trim() && !title.trim()) return setError("Describe what you can see — one line is enough.");

    setBusy(true);
    try {
      const form = new FormData();
      form.set("hazard_type", hazard);
      form.set("title", title.trim());
      form.set("description", description.trim());
      form.set("latitude", String(position.lat));
      form.set("longitude", String(position.lng));
      form.set("accuracy_m", String(coords && !pin ? coords.accuracy : 50));
      form.set("self_severity", String(severity));
      form.set("lang", i18n.language === "gar" ? "gar" : i18n.language === "hi" ? "hi" : "en");
      form.set("consent_media", String(consent));
      if (matched && matched.d < 8) form.set("ward_code", matched.w.code);
      if (photo) form.set("photo", photo);

      const res = await api.fileReport(form);
      setDone({
        code: res.report.code,
        message: res.message,
        merged: res.merged,
        confidence: res.confidence.value,
      });
      toast(res.merged ? "Added to an existing report nearby." : "Report filed.", "success");
    } catch (e) {
      const err = e as Error & { fields?: Record<string, string> };
      setError(err.fields ? Object.values(err.fields).join(" · ") : err.message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="max-w-xl mx-auto">
        <Card className="text-center !border-green-200" bodyClass="p-8">
          <div className="w-14 h-14 rounded-full bg-green-50 grid place-items-center mx-auto mb-4">
            <CheckCircle2 size={28} className="text-risk-green" />
          </div>
          <h1 className="text-xl mb-2">{done.merged ? "Added to a nearby report" : "Report received"}</h1>
          <p className="text-sm text-ink-600 leading-relaxed">{done.message}</p>
          <div className="grid grid-cols-2 gap-3 mt-6 text-left">
            <div className="panel-tight p-3">
              <p className="eyebrow">Reference</p>
              <p className="text-sm font-bold font-mono mt-1">{done.code}</p>
            </div>
            <div className="panel-tight p-3">
              <p className="eyebrow">Initial confidence</p>
              <p className="text-sm font-bold mt-1" style={{ color: LEVEL_COLOR.yellow }}>
                {Math.round(done.confidence * 100)}%
              </p>
            </div>
          </div>
          <p className="text-[11px] text-ink-400 mt-4 leading-relaxed">
            Confidence rises as neighbours corroborate and a field team verifies. If your report matches what the
            model already suspects, the control room sees both side by side.
          </p>
          <div className="flex gap-2 justify-center mt-6">
            <Link to="/" className="btn-primary">
              Back to the risk map
            </Link>
            <button
              className="btn-ghost"
              onClick={() => {
                setDone(null);
                setTitle("");
                setDescription("");
                setPhoto(null);
                setPin(null);
              }}
            >
              Report something else
            </button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <div className="max-w-3xl">
        <p className="eyebrow flex items-center gap-1.5">
          <ShieldAlert size={12} /> {t("report.title")}
        </p>
        <h1 className="text-2xl mt-1">{t("report.sub")}</h1>
        <p className="text-[13px] text-ink-500 mt-2 leading-relaxed">
          You do not need an account. Your exact position is shared with the district control room so a team can
          reach it, and your name is never shown on the public hazard feed.
          {!user && " Signing in lets the district weight your reports more heavily if you have been accurate before."}
        </p>
      </div>

      <div className="grid lg:grid-cols-[1fr_1fr] gap-5 items-start">
        <div className="grid gap-5">
          <Card title="1 · What are you seeing?">
            <div className="grid grid-cols-2 gap-2">
              {HAZARDS.map((h) => {
                const active = h.key === hazard;
                return (
                  <button
                    key={h.key}
                    onClick={() => setHazard(h.key)}
                    className={`text-left rounded-xl border px-3 py-2.5 transition-all ${
                      active
                        ? "border-risk-blue bg-risk-blue/5 ring-2 ring-risk-blue/25"
                        : "border-[var(--line)] hover:border-ink-300 bg-white"
                    }`}
                  >
                    <span className="block text-[13px] font-semibold text-ink-900">
                      {i18n.language === "hi" ? h.hi : i18n.language === "gar" ? h.gar : h.en}
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>

          <Card title="2 · How serious does it look?">
            <div className="flex gap-1.5">
              {SEVERITY.map((label, i) => {
                const value = i + 1;
                const level = (["green", "blue", "yellow", "orange", "red"] as const)[i];
                const active = severity === value;
                return (
                  <button
                    key={label}
                    onClick={() => setSeverity(value)}
                    className={`flex-1 rounded-lg py-2.5 text-[11px] font-bold transition-all ${
                      active ? "text-white shadow-md" : "bg-ink-100 text-ink-600 hover:bg-ink-200"
                    }`}
                    style={active ? { background: LEVEL_COLOR[level] } : undefined}
                  >
                    {value}
                  </button>
                );
              })}
            </div>
            <p className="text-[12px] text-ink-600 mt-2 font-medium">{SEVERITY[severity - 1]}</p>
            <p className="text-[11px] text-ink-400 mt-1">
              Your own read of the situation matters: residents reliably notice toe erosion and new cracks before any
              instrument does.
            </p>
          </Card>

          <Card title="3 · Describe it">
            <label className="label" htmlFor="title">
              One-line summary (optional)
            </label>
            <input
              id="title"
              className="input"
              placeholder="e.g. New crack above the tea stall, widening"
              value={title}
              maxLength={160}
              onChange={(e) => setTitle(e.target.value)}
            />
            <label className="label mt-4" htmlFor="desc">
              What you can see
            </label>
            <textarea
              id="desc"
              className="textarea"
              placeholder="Muddy water emerging from the hillside, trees leaning, sound of rocks moving…"
              value={description}
              maxLength={2000}
              onChange={(e) => setDescription(e.target.value)}
            />
            <p className="hint">{description.length}/2000 · plain language is better than technical language</p>

            <div className="mt-4">
              <label className="label">Photo (optional, max 8 MB)</label>
              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="hidden"
                onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              />
              {photo ? (
                <div className="flex items-center gap-3 panel-tight p-3">
                  <img
                    src={URL.createObjectURL(photo)}
                    alt="hazard preview"
                    className="w-14 h-14 object-cover rounded-lg shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-semibold truncate">{photo.name}</p>
                    <p className="text-[11px] text-ink-400">{(photo.size / 1024).toFixed(0)} KB attached</p>
                  </div>
                  <button className="btn-ghost btn-sm" onClick={() => setPhoto(null)}>
                    Remove
                  </button>
                </div>
              ) : (
                <button className="btn-ghost w-full border-dashed" onClick={() => fileInput.current?.click()}>
                  {photo ? <ImageOff size={15} /> : <Camera size={15} />} Add a photo from the scene
                </button>
              )}
            </div>
          </Card>
        </div>

        <div className="grid gap-5">
          <Card
            title="4 · Where is it?"
            subtitle={matched && matched.d < 8 ? `Nearest ward: ${matched.w.name}` : "Tap the map to drop a pin"}
            bodyClass="p-0"
            actions={
              <button className="btn-ghost btn-sm" onClick={locate} disabled={geoStatus === "asking"}>
                <Crosshair size={13} /> {geoStatus === "asking" ? "Finding…" : "Use GPS"}
              </button>
            }
          >
            <div className="h-[300px] relative">
              <RiskMap
                wards={wards}
                height="100%"
                markers={position ? [{ id: "you", lat: position.lat, lng: position.lng, kind: "shelter", label: "Reported hazard here", color: "#dc2626" }] : []}
                onSelectWard={() => undefined}
              />
              <div className="absolute inset-x-0 bottom-0 bg-white/92 backdrop-blur px-4 py-2.5 border-t border-[var(--line)] text-[11px] text-ink-600 flex items-center gap-2">
                <MapPin size={13} className="text-risk-red shrink-0" />
                {position ? (
                  <span className="font-mono">
                    {position.lat.toFixed(4)}, {position.lng.toFixed(4)}
                    {pin ? " · pinned by hand" : ` · GPS ±${coords?.accuracy ?? 0} m`}
                  </span>
                ) : (
                  <span>No location yet — allow GPS or tap the map.</span>
                )}
              </div>
            </div>
            <div className="p-4 grid gap-2">
              <button
                className="btn-soft btn-sm w-full"
                onClick={() => {
                  if (!position) return;
                  setPin({ lat: position.lat + 0.0004, lng: position.lng + 0.0004 });
                }}
              >
                Nudge the pin slightly
              </button>
              <MapPickPrompt wards={wards} onPick={(lat, lng) => setPin({ lat, lng })} />
              {matched && matched.d < 8 && (
                <p className="text-[11px] text-ink-400">
                  Routing to <strong className="text-ink-700">{matched.w.name}</strong> ({matched.d.toFixed(1)} km
                  away, currently {matched.w.level}).
                </p>
              )}
            </div>
          </Card>

          <Card title="Send it">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5 w-4 h-4 accent-blue-600 shrink-0"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span className="text-[12px] text-ink-600 leading-snug">{t("report.consent")}</span>
            </label>
            {error && (
              <div className="mt-4">
                <ErrorState error={error} compact />
              </div>
            )}
            <button className="btn-danger w-full mt-4" onClick={submit} disabled={busy}>
              {busy ? <Loading label={t("report.sending")} /> : <Send size={15} />}
              {t("report.submit")}
            </button>
            <p className="text-[11px] text-ink-400 mt-3 leading-relaxed flex gap-1.5">
              <TriangleAlert size={13} className="shrink-0 mt-px" />
              If you are in immediate danger, do not fill this in — call 112, or the Uttarakhand control room on 1070.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Lets a reviewer without GPS still place a pin, by picking a ward. */
function MapPickPrompt({ wards, onPick }: { wards: WardRiskSummary[]; onPick: (lat: number, lng: number) => void }) {
  const [code, setCode] = useState("");
  const ward = wards.find((w) => w.code === code);
  return (
    <div className="flex items-center gap-2">
      <select
        className="select !py-2 !text-[13px]"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        aria-label="Choose a ward instead of using GPS"
      >
        <option value="">…or pick a ward from the list</option>
        {wards.map((w) => (
          <option key={w.code} value={w.code}>
            {w.district} — {w.name}
          </option>
        ))}
      </select>
      <button
        className="btn-ghost btn-sm shrink-0"
        disabled={!ward}
        onClick={() => ward && onPick(ward.latitude, ward.longitude)}
      >
        Set
      </button>
    </div>
  );
}

function dist(a: number, b: number, c: number, d: number) {
  const R = 6371;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const h =
    Math.sin(toRad(c - a) / 2) ** 2 +
    Math.cos(toRad(a)) * Math.cos(toRad(c)) * Math.sin(toRad(d - b) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
