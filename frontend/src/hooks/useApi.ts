import { useCallback, useEffect, useRef, useState } from "react";

export interface ApiState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
}

/** Run an api.* call, re-running when `deps` change. Ignores stale responses. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[], enabled = true): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const call = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const id = ++call.current;
    setLoading(true);
    setError(undefined);
    fn()
      .then((d) => id === call.current && setData(d))
      .catch((e: Error) => id === call.current && setError(e))
      .finally(() => id === call.current && setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
