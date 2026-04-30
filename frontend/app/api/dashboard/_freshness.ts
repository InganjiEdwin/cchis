import type {
  AlertRecord,
  DashboardFreshnessSummary,
  IngestionRunRecord,
  LatestWardRisk,
  ModelRunRecord,
} from "@/lib/dashboard";

export function maxTimestamp(...timestamps: Array<string | null>) {
  return timestamps.reduce<string | null>((latest, value) => {
    if (!value) {
      return latest;
    }
    if (!latest || new Date(value).getTime() > new Date(latest).getTime()) {
      return value;
    }
    return latest;
  }, null);
}

export function buildFreshnessSummary(
  modelTimestamp: string | null,
  dataSyncTimestamp: string | null,
  alertTimestamp: string | null,
  predictionTimestamp: string | null,
): DashboardFreshnessSummary {
  const timestamps = [modelTimestamp, dataSyncTimestamp, alertTimestamp, predictionTimestamp].filter(Boolean) as string[];
  const latest = timestamps.reduce<number | null>((current, value) => {
    const next = new Date(value).getTime();
    if (Number.isNaN(next)) {
      return current;
    }
    return current == null || next > current ? next : current;
  }, null);
  const ageMinutes = latest == null ? Number.POSITIVE_INFINITY : (Date.now() - latest) / 60000;

  return {
    last_model_run_at: modelTimestamp,
    last_data_sync_at: dataSyncTimestamp,
    last_alert_ingestion_at: alertTimestamp,
    prediction_generated_at: predictionTimestamp,
    freshness_state: ageMinutes > 360 ? "stale" : ageMinutes > 120 ? "delayed" : "fresh",
  };
}

export function getLatestAlertTimestamp(alerts: AlertRecord[]) {
  return alerts.reduce<string | null>((latest, alert) => {
    if (!latest || new Date(alert.created_at).getTime() > new Date(latest).getTime()) {
      return alert.created_at;
    }
    return latest;
  }, null);
}

export function getLatestPredictionTimestamp(latestRisks: LatestWardRisk[]) {
  return maxTimestamp(...latestRisks.map((risk) => risk.generated_at));
}

export function getLatestModelRunTimestamp(modelRuns: ModelRunRecord[]) {
  return modelRuns[0]?.completed_at ?? modelRuns[0]?.started_at ?? null;
}

export function getLatestDataSyncTimestamp(ingestionRuns: IngestionRunRecord[]) {
  return ingestionRuns[0]?.completed_at ?? ingestionRuns[0]?.started_at ?? null;
}
