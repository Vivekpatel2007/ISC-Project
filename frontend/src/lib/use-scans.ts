"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "./api-client";
import type { ScanMetadata } from "./types";

interface RepositoryResult {
  token: string;
  key: string;
  scans: ScanMetadata[];
  error: string | null;
}

export function useScans(token: string | null) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<RepositoryResult | null>(null);
  const key = `${token}:${revision}`;
  useEffect(() => {
    if (!token) return;
    let active = true;
    apiClient
      .listScans(token)
      .then((scans) => {
        if (active) setResult({ token, key, scans, error: null });
      })
      .catch((error: unknown) => {
        if (active)
          setResult((previous) => ({
            token,
            key,
            scans: previous?.token === token ? previous.scans : [],
            error:
              error instanceof Error
                ? error.message
                : "Unable to load scan records. Please try again.",
          }));
      });
    return () => {
      active = false;
    };
  }, [token, key]);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  return {
    scans: result?.token === token ? result.scans : [],
    loading: Boolean(token) && result?.key !== key,
    error: result?.key === key ? result.error : null,
    refresh,
  };
}
