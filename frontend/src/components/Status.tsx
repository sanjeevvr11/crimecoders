import type { ReactNode } from "react";
import type { ApiState } from "../hooks";

export const Loading = ({ what = "data" }: { what?: string }) => (
  <div className="status loading" role="status"><span className="spinner" aria-hidden="true" /> Loading {what}…</div>
);

export const ErrorBox = ({ error, onRetry }: { error: Error; onRetry?: () => void }) => (
  <div className="status error" role="alert">
    <b>Could not load.</b> {error.message}
    {error.message.includes("pipeline") || error.message.includes("Failed to fetch") ? (
      <div className="muted">Is the API running (make api) and has the pipeline been run (make pipeline)?</div>
    ) : null}
    {onRetry && <button onClick={onRetry}>Retry</button>}
  </div>
);

export const Empty = ({ children }: { children: ReactNode }) => <div className="status empty muted">{children}</div>;

/** Renders loading / error / empty states for a hook result, else children(data). */
export function Async<T>({ state, what, isEmpty, empty, children }: {
  state: ApiState<T>;
  what?: string;
  isEmpty?: (d: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (state.loading && state.data === undefined) return <Loading what={what} />;
  if (state.error) return <ErrorBox error={state.error} onRetry={state.reload} />;
  if (state.data === undefined) return null;
  if (isEmpty?.(state.data)) return <Empty>{empty ?? "Nothing to show."}</Empty>;
  return <>{children(state.data)}</>;
}
