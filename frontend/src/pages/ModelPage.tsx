import { BookOpen, Cpu, Database, Eye, ShieldCheck, TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import { Bar, Card, ErrorState, LEVEL_COLOR, Loading, formatNumber } from "../components/ui";
import { PageHeader } from "../components/Layout";
import { useAsync } from "../hooks";

/**
 * The model card. Judges — and, more importantly, a district magistrate
 * deciding whether to order an evacuation — should be able to read exactly what
 * this system is and is not without asking a single question. So the weights,
 * thresholds, data lineage and the limits are all on one page, unpadded.
 */
export default function ModelPage() {
  const model = useAsync(() => api.model(), []);
  const data = model.data;

  if (model.loading && !data) return <Loading label="Loading model card…" />;
  if (model.error) return <ErrorState error={model.error} onRetry={model.reload} />;
  if (!data) return null;

  const dynamic = data.factor_docs.filter((f) => f.kind === "dynamic" || f.kind === "forecast");
  const statics = data.factor_docs.filter((f) => f.kind === "static");

  return (
    <div className="grid gap-5">
      <PageHeader
        eyebrow="Transparency"
        title="How AapaatSathi decides, and what it cannot tell you"
        sub="Every published weight, the exact thresholds, where each input comes from, and a plain statement of the limits. Nothing on this page is a black box."
        actions={<span className="pill font-mono">{data.version}</span>}
      />

      <div
        className="rounded-2xl border px-5 py-4 flex gap-3 items-start"
        style={{ background: "#fff7ed", borderColor: "#fed7aa" }}
      >
        <TriangleAlert size={20} className="text-risk-orange shrink-0 mt-0.5" />
        <div>
          <p className="text-[14px] font-bold text-ink-950">Read this before you act on a score</p>
          <p className="text-[13px] text-ink-700 leading-relaxed mt-1">{data.disclaimer}</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card
          title="Factor weights"
          subtitle={`Ten factors, weights summing to ${data.weights_sum.toFixed(2)}. Contribution = normalised × weight × 100.`}
          actions={
            <span className="pill">
              <Cpu size={12} /> {data.active_config}
            </span>
          }
        >
          <div className="grid gap-3.5">
            {[...dynamic, ...statics].map((f) => (
              <div key={f.key}>
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <span className="text-[13px] font-semibold text-ink-900 truncate">{f.name}</span>
                  <span className="text-[12px] font-bold tabular text-ink-700 shrink-0">
                    {(f.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <Bar value={f.weight} max={0.18} color={f.kind === "static" ? "#8ea0bd" : "#0ea5e9"} height={6} />
                <p className="text-[11px] text-ink-400 mt-1">
                  <span
                    className="chip !text-[9px] !px-1.5 !py-0 mr-1.5"
                    style={{
                      background: f.kind === "static" ? "#eef2f8" : "#e0f2fe",
                      color: f.kind === "static" ? "#5b6b86" : "#0369a1",
                    }}
                  >
                    {f.kind}
                  </span>
                  {f.source}
                </p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-ink-400 mt-4 pt-3 divider leading-relaxed">
            Static terrain terms never change within a season, which is exactly why they cannot be the whole answer:
            a dry slope at 38° is not dangerous, and the dynamic terms are what move the score.
          </p>
        </Card>

        <div className="grid gap-5 content-start">
          <Card title="Alert thresholds" subtitle="Where each level begins. Orange and red are the actionable band.">
            <div className="grid gap-2">
              {(["green", "blue", "yellow", "orange", "red"] as const).map((level) => {
                const floor = level === "green" ? 0 : data.thresholds[level];
                const ceil =
                  level === "red" ? 100 : data.thresholds[({ blue: "yellow", yellow: "orange", orange: "red" } as Record<string, string>)[level]] ?? 100;
                return (
                  <div key={level} className="flex items-center gap-3">
                    <span className="w-24 shrink-0">
                      <span className="chip" style={{ background: LEVEL_COLOR[level], color: "#fff" }}>
                        {level}
                      </span>
                    </span>
                    <div className="flex-1 h-6 rounded-md bg-ink-100 relative overflow-hidden">
                      <div
                        className="absolute inset-y-0 rounded-r-md"
                        style={{
                          left: `${floor}%`,
                          width: `${Math.max(2, (ceil as number) - floor)}%`,
                          background: LEVEL_COLOR[level],
                          opacity: 0.85,
                        }}
                      />
                    </div>
                    <span className="text-[11px] font-mono tabular text-ink-600 w-20 text-right shrink-0">
                      {floor}–{level === "red" ? 100 : (ceil as number) - 1}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] text-ink-400 mt-3 leading-relaxed">
              Crowds move this by multiplying, capped at ×{data.crowd_uplift_cap.toFixed(2)} — enough for three
              corroborated reports to lift a yellow ward into orange, never enough to fabricate a red on its own.
            </p>
          </Card>

          <Card title="Data lineage" bodyClass="p-0">
            <ul className="divide-y divide-[var(--line)]">
              <Line Icon={Database} label="Rainfall nowcast & forecast" value="Open-Meteo (live mode) or a deterministic monsoon simulator; every row tagged with its source." />
              <Line Icon={Eye} label="Slope & elevation" value="SRTM / CartDEM 30 m derived — approximated in this build, to be replaced with a surveyed DEM." />
              <Line Icon={BookOpen} label="Lithology & thrust traces" value="Geological Survey of India National Geomorphoscape; MBT / MCT fault proximity." />
              <Line Icon={ShieldCheck} label="Vegetation deficit" value="Sentinel-2 NDVI anomaly against a 0.75 mid-elevation forest reference." />
              <Line Icon={Eye} label="Ground truth" value="Resident reports, weighted by corroboration, evidence and reporter history." />
            </ul>
          </Card>
        </div>
      </div>

      <Card title="Report trust scoring" subtitle="The same argument applies to crowd reports: no hidden model.">
        <div className="grid sm:grid-cols-5 gap-3">
          {[
            ["Reporter history", 0.3, "#0ea5e9"],
            ["Corroboration", 0.25, "#16a34a"],
            ["Evidence attached", 0.2, "#f97316"],
            ["Severity signal", 0.15, "#8ea0bd"],
            ["Geo plausibility", 0.1, "#ca8a04"],
          ].map(([label, weight, color]) => (
            <div key={label as string} className="panel-tight p-3">
              <p className="text-[11px] font-semibold text-ink-600 leading-snug">{label as string}</p>
              <p className="text-lg font-extrabold tabular mt-1" style={{ color: color as string }}>
                {Math.round((weight as number) * 100)}%
              </p>
              <div className="mt-1.5">
                <Bar value={weight as number} max={0.3} color={color as string} height={4} />
              </div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-ink-400 mt-4 leading-relaxed">
          An anonymous report is not disbelieved — it is weighted lower. Confirmation by a field responder raises the
          reporter's trust score; a dismissal lowers it. That feedback loop is the only thing that makes crowd data
          usable during a real event instead of a rumour amplifier.
        </p>
      </Card>

      <div className="grid sm:grid-cols-3 gap-4">
        {[
          ["What this is", "A decision-support prior that ranks which ward to check first, and a delivery channel that reaches people without smartphones."],
          ["What this is not", "A prediction that a specific slope will fail at a specific time, and not a substitute for an engineer's site assessment."],
          ["What must happen before operational use", "Swap the seeded terrain and population priors for GSI / Survey of India / State DGRRM layers, and calibrate thresholds against a recorded event ledger."],
        ].map(([title, body], i) => (
          <div key={title} className={`panel p-4 ${i === 1 ? "border-risk-orange/40" : ""}`}>
            <p className="eyebrow">{title}</p>
            <p className="text-[13px] text-ink-700 leading-relaxed mt-2">{body}</p>
          </div>
        ))}
      </div>

      <p className="text-[11px] text-ink-400 pb-2">
        Coverage in this build: 8 districts, 40 wards, {formatNumber(210_200)} residents represented. Full source at
        the repository linked in the submission.
      </p>
    </div>
  );
}

function Line({ Icon, label, value }: { Icon: typeof Eye; label: string; value: string }) {
  return (
    <li className="px-4 py-3 flex gap-3">
      <Icon size={15} className="text-ink-400 mt-0.5 shrink-0" />
      <div>
        <p className="text-[12px] font-bold text-ink-900">{label}</p>
        <p className="text-[11px] text-ink-600 leading-relaxed mt-0.5">{value}</p>
      </div>
    </li>
  );
}
