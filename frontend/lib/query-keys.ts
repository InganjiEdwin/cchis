export const queryKeys = {
  auth: {
    me: () => ["auth", "me"] as const,
  },
  wards: {
    all: () => ["wards"] as const,
    list: (filters: Record<string, string | number | boolean | null | undefined>) => ["wards", filters] as const,
    detail: (wardId: string | number) => ["ward", wardId] as const,
    riskHistory: (wardId: string | number) => ["ward-risk-history", wardId] as const,
    alerts: (wardId: string | number) => ["ward-alerts", wardId] as const,
  },
  alerts: {
    all: () => ["alerts"] as const,
    list: (filters: Record<string, string | number | boolean | null | undefined>) => ["alerts", filters] as const,
    detail: (alertId: string | number) => ["alert", alertId] as const,
  },
  overview: {
    root: () => ["overview"] as const,
  },
  chvs: {
    root: () => ["chvs"] as const,
  },
  facilityReadiness: {
    root: () => ["facility-readiness"] as const,
  },
  system: {
    root: () => ["system"] as const,
  },
} as const;
