import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/**
 * Last line of defence. A blank white screen during a live demonstration is the
 * worst possible outcome, so a crash renders a readable panel with the actual
 * message and a way back, instead of killing the whole app tree.
 */
export class ErrorBoundary extends Component<{ children: ReactNode; label?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AapaatSathi] UI error boundary caught:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="min-h-[60vh] grid place-items-center p-6">
        <div className="panel max-w-lg w-full p-6">
          <p className="eyebrow text-risk-orange">Interface problem</p>
          <h2 className="text-xl mt-1 mb-2">This view stopped responding</h2>
          <p className="text-sm text-ink-600 leading-relaxed">
            {this.props.label ? `While loading ${this.props.label}: ` : ""}
            <code className="text-xs font-mono bg-ink-100 px-1.5 py-0.5 rounded break-all">
              {error.message}
            </code>
          </p>
          <p className="text-xs text-ink-400 mt-3 leading-relaxed">
            Warnings still reach residents by SMS and voice call — this page is only the display.
            If you are in the district control room, note the time and reload.
          </p>
          <div className="flex gap-2 mt-5">
            <button className="btn-primary" onClick={() => this.setState({ error: null })}>
              Try this view again
            </button>
            <button className="btn-ghost" onClick={() => window.location.assign("/")}>
              Back to the risk map
            </button>
          </div>
        </div>
      </div>
    );
  }
}
