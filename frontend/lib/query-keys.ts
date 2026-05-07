type QueryFilterValue = string | number | boolean | null | undefined | readonly (string | number | boolean)[];
type QueryFilters = Record<string, QueryFilterValue>;

export const queryKeys = {
  auth: {
    me: () => ["auth", "me"] as const,
    policyAcceptance: () => ["auth", "policy-acceptance"] as const,
    activity: (filters?: QueryFilters) =>
      ["auth", "activity", filters ?? {}] as const,
    recoveryCodes: () => ["auth", "recovery-codes"] as const,
  },
  wards: {
    all: () => ["wards"] as const,
    list: (filters: QueryFilters) => ["wards", filters] as const,
    detail: (wardId: string | number) => ["ward", wardId] as const,
    riskHistory: (wardId: string | number) => ["ward-risk-history", wardId] as const,
    alerts: (wardId: string | number) => ["ward-alerts", wardId] as const,
  },
  alerts: {
    all: () => ["alerts"] as const,
    list: (filters: QueryFilters) => ["alerts", filters] as const,
    detail: (alertId: string | number) => ["alert", alertId] as const,
    trigger: {
      context: (wardId: string | number) => ["alerts", "trigger", "context", wardId] as const,
      preview: (wardId: string | number, triggerType: string, messageOverride: string | null = null) =>
        ["alerts", "trigger", "preview", wardId, triggerType, messageOverride] as const,
      requestStatus: (requestId: string) => ["alerts", "trigger", "request-status", requestId] as const,
    },
  },
  overview: {
    root: () => ["overview"] as const,
  },
  topbar: {
    root: () => ["topbar"] as const,
  },
  chvs: {
    root: () => ["chvs"] as const,
    activity: (publicId: string) => ["chvs", "activity", publicId] as const,
    messages: (publicId: string) => ["chvs", "messages", publicId] as const,
    coverageRequests: {
      all: () => ["chvs", "coverage-requests"] as const,
      list: (filters: QueryFilters) =>
        ["chvs", "coverage-requests", filters] as const,
      detail: (publicId: string) => ["chvs", "coverage-requests", publicId] as const,
    },
  },
  maps: {
    wards: () => ["maps", "wards"] as const,
  },
  facilityReadiness: {
    root: () => ["facility-readiness"] as const,
    detail: (facilityId: string | number) => ["facility-readiness", facilityId] as const,
  },
  preparednessActions: {
    root: () => ["preparedness-actions"] as const,
    list: (filters: QueryFilters) =>
      ["preparedness-actions", filters] as const,
    detail: (publicId: string) => ["preparedness-actions", publicId] as const,
  },
  system: {
    root: () => ["system"] as const,
  },
  operationalMetrics: {
    root: () => ["operational-metrics"] as const,
    dashboard: (filters: QueryFilters) => ["operational-metrics", filters] as const,
  },
  modelHealth: {
    root: () => ["model-health"] as const,
  },
  interoperability: {
    root: () => ["interoperability"] as const,
    dashboard: () => ["interoperability", "dashboard"] as const,
  },
  sourceData: {
    root: () => ["source-data"] as const,
    feedTypes: () => ["source-data", "feed-types"] as const,
    uploads: (filters: QueryFilters = {}) => ["source-data", "uploads", filters] as const,
    upload: (publicId: string) => ["source-data", "upload", publicId] as const,
  },
  messageGovernance: {
    root: () => ["message-governance"] as const,
    dashboard: (filters: QueryFilters) => ["message-governance", filters] as const,
    template: (publicId: string) => ["message-governance", "template", publicId] as const,
  },
} as const;
