import { CheckCircle2, ClipboardList, MinusCircle, Route, Send, Truck, XCircle } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { HazardReport, Level } from "../api/types";
import { Card, EmptyState, ErrorState, LEVEL_COLOR, LevelBadge, SkeletonRows, timeAgo, useToast } from "../components/ui";
import { PageHeader } from "../components/Layout";
import { useAsync, useNow } from "../hooks";
import { useLive } from "../state/live";
import { useSession } from "../state/session";

/**
 * The responder surface. Its whole job is to make verification fast enough that
 * it actually happens on a wet afternoon: the two buttons that matter are
 * confirm and dismiss, and each one feeds the reporter-trust loop.
 */
export default function Responder() {
  const { revision } = useLive();
  const now = useNow();
  const toast = useToast();
  const { user } = useSession();
  const [filter, setFilter] = useState<"needs_review" | "new" | "all">("needs_review");

  const queue = useAsync(
    () =>
      api.reports(
        filter === "needs_review"
          ? { needs_review: true }
          : filter === "new"
            ? { status: "new" }
            : {},
      ),
    [filter, revision],
  );
  const roads = useAsync(() => api.roads(), [revision]);
  const shelters = useAsync(() => api.shelters({}), [revision]);

  const reports = queue.data?.reports ?? [];
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const act = async (code: string, status: string, message: string) => {
    setBusy(code);
    try {
      await api.verdict(code, status, note[code] ?? "");
      toast(message, "success");
      await queue.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const blocked = (roads.data?.roads ?? []).filter((r) => r.status !== "open");

  return (
    <div className="grid gap-5">
      <PageHeader
        eyebrow="Field team"
        title="Verification queue"
        sub={`Signed in as ${user?.full_name} · ${user?.role.replace("_", " ")}. Your verdicts adjust the reporter's trust score, which changes how the model weighs their next report.`}
        actions={
          <div className="flex gap-1 rounded-xl bg-ink-100 p-1">
            {(["needs_review", "new", "all"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-colors ${
                  filter === f ? "bg-white shadow-sm text-ink-900" : "text-ink-500"
                }`}
              >
                {f === "needs_review" ? "Open" : f}
              </button>
            ))}
          </div>
        }
      />

      {queue.error && <ErrorState error={queue.error} onRetry={queue.reload} />}

      <div className="grid lg:grid-cols-[1.5fr_1fr] gap-5 items-start">
        <Card title={`Reports to triage (${reports.length})`} subtitle="Ordered by confidence, strongest evidence first." bodyClass="p-0">
          {queue.loading && reports.length === 0 ? (
            <div className="p-4">
              <SkeletonRows rows={4} height={120} />
            </div>
          ) : reports.length === 0 ? (
            <EmptyState title="Queue is clear" hint="Nothing unverified in the last week." icon={<CheckCircle2 size={18} />} />
          ) : (
            <ul className="divide-y divide-[var(--line)]">
              {reports.map((r) => (
                <QueueItem
                  key={r.code}
                  report={r}
                  now={now}
                  busy={busy === r.code}
                  note={note[r.code] ?? ""}
                  onNote={(v) => setNote((p) => ({ ...p, [r.code]: v }))}
                  onConfirm={() => act(r.code, "confirmed", `Confirmed ${r.code}. Ward confidence raised.`)}
                  onDismiss={() => act(r.code, "dismissed", `Dismissed ${r.code}. Reporter trust lowered.`)}
                  onDispatch={async () => {
                    setBusy(r.code);
                    try {
                      await api.dispatchReport(r.code);
                      toast(`Team dispatched for ${r.code}.`, "success");
                      await queue.reload();
                    } catch (e) {
                      toast((e as Error).message, "error");
                    } finally {
                      setBusy(null);
                    }
                  }}
                />
              ))}
            </ul>
          )}
        </Card>

        <div className="grid gap-5 content-start">
          <Card
            title="Roads you can update"
            subtitle="Marking a lifeline closed changes the shelter routing the control room sees."
            bodyClass="p-0"
          >
            {roads.loading ? (
              <div className="p-4">
                <SkeletonRows rows={3} height={48} />
              </div>
            ) : (
              <ul className="divide-y divide-[var(--line)] max-h-[300px] overflow-y-auto">
                {(roads.data?.roads ?? []).slice(0, 12).map((r) => (
                  <li key={r.code} className="px-4 py-2.5">
                    <p className="text-[12px] font-semibold truncate">{r.name}</p>
                    <div className="flex gap-1 mt-1.5">
                      {(["open", "caution", "partial", "closed"] as const).map((s) => (
                        <button
                          key={s}
                          onClick={async () => {
                            try {
                              await api.updateRoad(r.code, { status: s, note: r.note });
                              toast(`${r.code} → ${s}`, "success");
                              await roads.reload();
                            } catch (e) {
                              toast((e as Error).message, "error");
                            }
                          }}
                          className="px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wide transition-all"
                          style={
                            r.status === s
                              ? { background: LEVEL_COLOR[s as unknown as Level] ?? (s === "open" ? "#16a34a" : s === "caution" ? "#ca8a04" : s === "partial" ? "#f97316" : "#dc2626"), color: "#fff" }
                              : { background: "#f1f5f9", color: "#64748b" }
                          }
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Shelter occupancy"
            subtitle={`Blocked routes in your view: ${blocked.length}`}
            bodyClass="p-0"
            actions={
              <span className="pill">
                <Route size={12} /> {shelters.data?.total_free ?? 0} free places
              </span>
            }
          >
            <ul className="divide-y divide-[var(--line)] max-h-[280px] overflow-y-auto">
              {(shelters.data?.shelters ?? []).slice(0, 8).map((s) => (
                <li key={s.code} className="px-4 py-2.5 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-semibold truncate">{s.name}</p>
                    <p className="text-[10px] text-ink-400 tabular">
                      {s.occupied}/{s.capacity} occupied · {s.free_places} free
                    </p>
                  </div>
                  {[
                    { label: "−5", delta: -5, Icon: MinusCircle },
                    { label: "+5", delta: 5, Icon: Send },
                  ].map(({ label, delta, Icon }) => (
                    <button
                      key={label}
                      onClick={async () => {
                        try {
                          await api.updateShelter(s.code, { occupied: Math.max(0, s.occupied + delta) });
                          await shelters.reload();
                        } catch (e) {
                          toast((e as Error).message, "error");
                        }
                      }}
                      className="w-7 h-7 grid place-items-center rounded-lg bg-ink-100 hover:bg-ink-200 text-ink-600"
                      title={`${label} arrivals`}
                    >
                      <Icon size={13} />
                    </button>
                  ))}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function QueueItem({
  report: r,
  now,
  busy,
  note,
  onNote,
  onConfirm,
  onDismiss,
  onDispatch,
}: {
  report: HazardReport;
  now: number;
  busy: boolean;
  note: string;
  onNote: (v: string) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  onDispatch: () => void;
}) {
  return (
    <li className="px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-bold text-ink-900">{r.title || r.hazard_type}</p>
          <p className="text-[11px] text-ink-400">
            {r.hazard_type.replace("_", " ")} · {r.ward_name ?? "unassigned"} · {timeAgo(r.created_at, now)} · via{" "}
            {r.source}
          </p>
        </div>
        <div className="text-right shrink-0">
          <LevelBadge level={(r.status === "confirmed" ? "red" : r.status === "under_review" ? "orange" : "yellow") as Level} size="sm" label={`${Math.round(r.confidence * 100)}% trust`} showDot={false} />
          <p className="text-[10px] text-ink-400 mt-1">{r.corroborated_by} corroborations</p>
        </div>
      </div>

      <p className="text-[12px] text-ink-600 mt-2 leading-relaxed">{r.description}</p>

      {r.photo_url && (
        <a href={r.photo_url} target="_blank" rel="noreferrer" className="mt-2 inline-block">
          <img src={r.photo_url} alt="hazard" className="h-24 rounded-lg object-cover border border-[var(--line)]" />
        </a>
      )}

      <div className="flex flex-wrap items-center gap-2 mt-3">
        <input
          className="input !py-1.5 !text-[12px] flex-1 min-w-[10rem]"
          placeholder="Note for the record (optional)"
          value={note}
          onChange={(e) => onNote(e.target.value)}
        />
        <button className="btn btn-sm" style={{ background: "#16a34a", color: "#fff" }} onClick={onConfirm} disabled={busy}>
          <CheckCircle2 size={13} /> Confirm
        </button>
        <button className="btn-ghost btn-sm" onClick={onDispatch} disabled={busy} title="Task a field team">
          <Truck size={13} /> Dispatch
        </button>
        <button className="btn-ghost btn-sm !text-risk-red" onClick={onDismiss} disabled={busy}>
          <XCircle size={13} /> Dismiss
        </button>
      </div>

      {r.responders_dispatched > 0 && (
        <p className="text-[10px] text-ink-400 mt-2 flex items-center gap-1">
          <ClipboardList size={11} /> {r.responders_dispatched} team(s) tasked · status {r.status.replace("_", " ")}
        </p>
      )}
    </li>
  );
}
