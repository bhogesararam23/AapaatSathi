import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { API_ROOT } from "../api/client";
import type { LiveEvent } from "../api/types";

type Status = "connecting" | "open" | "closed" | "error";

interface LiveValue {
  status: Status;
  events: LiveEvent[];
  /** Increments on any event the UI should refetch for. */
  revision: number;
  /** Count of risk updates since mount — cheap way to show "live". */
  updates: number;
  connect: () => void;
  disconnect: () => void;
  subscribe: (handler: (e: LiveEvent) => void) => () => void;
}

const Ctx = createContext<LiveValue | null>(null);

const RECONNECT_FLOOR = 1500;
const RECONNECT_CEILING = 20_000;

/**
 * One shared WebSocket for the whole app.
 *
 * Exponential backoff with jitter matters here: a watch-room tab stays open for
 * hours on a hotel Wi-Fi that drops constantly, and a naive reconnect loop would
 * hammer the server the moment the network returns.
 */
export function LiveProvider({
  channel = "public",
  token = "",
  children,
}: {
  channel?: "public" | "ops";
  token?: string;
  children: ReactNode;
}) {
  const [status, setStatus] = useState<Status>("connecting");
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [revision, setRevision] = useState(0);
  const [updates, setUpdates] = useState(0);

  const socket = useRef<WebSocket | null>(null);
  const attempts = useRef(0);
  const timer = useRef<number | null>(null);
  const closedByUs = useRef(false);
  const handlers = useRef(new Set<(e: LiveEvent) => void>());

  const subscribe = useCallback((handler: (e: LiveEvent) => void) => {
    handlers.current.add(handler);
    return () => handlers.current.delete(handler);
  }, []);

  const disconnect = useCallback(() => {
    closedByUs.current = true;
    if (timer.current) window.clearTimeout(timer.current);
    socket.current?.close();
    socket.current = null;
    setStatus("closed");
  }, []);

  const connect = useCallback(() => {
    closedByUs.current = false;
    if (typeof WebSocket === "undefined") {
      setStatus("error");
      return;
    }
    // Same-origin "/api" so the Vite proxy (and any reverse proxy) handles it.
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const absolute = import.meta.env.VITE_API_BASE as string | undefined;
    const host = absolute ? absolute.replace(/^http/, "ws").replace(/\/$/, "") : `${proto}://${window.location.host}`;
    const url = `${host}${API_ROOT}/ws?channel=${channel}${token ? `&token=${encodeURIComponent(token)}` : ""}`;

    setStatus("connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      setStatus("error");
      return;
    }
    socket.current = ws;

    ws.onopen = () => {
      attempts.current = 0;
      setStatus("open");
    };
    ws.onmessage = (raw) => {
      let parsed: LiveEvent;
      try {
        parsed = JSON.parse(raw.data as string) as LiveEvent;
      } catch {
        return;
      }
      if (parsed.event === "replay" && Array.isArray(parsed.data)) {
        const replay = parsed.data as LiveEvent[];
        setEvents((prev) => [...replay, ...prev].slice(0, 120));
        replay.forEach((e) => handlers.current.forEach((h) => h(e)));
        return;
      }
      if (parsed.event === "pong") return;
      setEvents((prev) => [parsed, ...prev].slice(0, 120));
      setUpdates((n) => n + 1);
      // Risk ticks are frequent; only structural events force a refetch.
      if (parsed.event !== "risk:update") setRevision((n) => n + 1);
      handlers.current.forEach((h) => h(parsed));
    };
    ws.onerror = () => setStatus("error");
    ws.onclose = () => {
      socket.current = null;
      if (closedByUs.current) {
        setStatus("closed");
        return;
      }
      setStatus("connecting");
      const base = Math.min(RECONNECT_CEILING, RECONNECT_FLOOR * 2 ** attempts.current);
      attempts.current += 1;
      const delay = base / 2 + Math.random() * (base / 2);
      timer.current = window.setTimeout(connect, delay);
    };
  }, [channel, token]);

  useEffect(() => {
    connect();
    return () => {
      closedByUs.current = true;
      if (timer.current) window.clearTimeout(timer.current);
      socket.current?.close();
    };
  }, [connect]);

  // Heartbeat keeps proxies from reaping an idle socket mid-presentation.
  useEffect(() => {
    if (status !== "open") return;
    const id = window.setInterval(() => {
      if (socket.current?.readyState === WebSocket.OPEN) socket.current.send("ping");
    }, 25_000);
    return () => window.clearInterval(id);
  }, [status]);

  const value = useMemo(
    () => ({ status, events, revision, updates, connect, disconnect, subscribe }),
    [status, events, revision, updates, connect, disconnect, subscribe],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): LiveValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLive must be used inside <LiveProvider>");
  return ctx;
}
