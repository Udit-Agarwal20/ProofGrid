"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<{
    key: string | null;
    data?: T;
    error?: unknown;
    loading: boolean;
  }>({ key: path, loading: !!path });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState((previous) => ({
      key: path,
      data: previous.key === path ? previous.data : undefined,
      loading: true,
    }));
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ key: path, data, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ key: path, error, loading: false });
      });
    return () => controller.abort();
  }, [path, revision]);
  return {
    ...(state.key === path
      ? state
      : { loading: !!path, data: undefined, error: undefined }),
    reload,
  };
}
export function useDebounce<T>(value: T, delay = 300) {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setResult(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return result;
}
