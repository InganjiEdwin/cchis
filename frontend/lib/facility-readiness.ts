import type { AlertRecord, FacilityRecord, LatestWardRisk } from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";

export type FacilityRow = {
  id: string;
  facilityId: number;
  facilityName: string;
  facilityType: string;
  wardId: number;
  wardName: string;
  subCounty: string;
  surgeRisk: "EXTREME" | "MODERATE" | "LOW";
  projectedCases: number;
  orsStockPercent: number;
  orsState: "CRITICAL" | "STABLE" | "READY";
  staffingFilled: number;
  staffingRequired: number;
  staffingState: "LIMITED" | "OPTIMAL";
  lastReported: string;
  lastReportedMinutes: number;
  freshnessState: "FRESH" | "WARNING" | "STALE";
};

export function toSurgeRisk(level: FacilityRecord["ward_risk_level"]): FacilityRow["surgeRisk"] {
  if (level === "HIGH") {
    return "EXTREME";
  }
  if (level === "MEDIUM") {
    return "MODERATE";
  }
  return "LOW";
}

export function toOrsState(percent: number): FacilityRow["orsState"] {
  if (percent < 30) {
    return "CRITICAL";
  }
  if (percent < 75) {
    return "STABLE";
  }
  return "READY";
}

export function formatFacilityType(facility: FacilityRecord) {
  const label = facility.facility_type.replaceAll("_", " ").toLowerCase();
  const level = facility.level.replaceAll("_", " ").replace("LEVEL ", "Level ");
  return `${level} ${label}`.replace(/\b\w/g, (character) => character.toUpperCase());
}

export function getMinutesSince(timestamp: string) {
  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) {
    return Number.POSITIVE_INFINITY;
  }
  return Math.max(0, Math.round((Date.now() - value) / 60000));
}

export function toFreshnessState(minutes: number): FacilityRow["freshnessState"] {
  if (minutes > 120) {
    return "STALE";
  }
  if (minutes > 30) {
    return "WARNING";
  }
  return "FRESH";
}

export function formatFacilityLastReported(timestamp: string) {
  const minutes = getMinutesSince(timestamp);
  return {
    label: formatRelativeTimestamp(timestamp),
    minutes,
    freshnessState: toFreshnessState(minutes),
  };
}

export function buildFacilityRows(facilities: FacilityRecord[], risks: LatestWardRisk[]): FacilityRow[] {
  const riskMap = new Map<number, LatestWardRisk>();
  risks.forEach((risk) => {
    riskMap.set(risk.ward_id, risk);
  });

  return facilities.map((facility) => {
    const risk = riskMap.get(facility.ward);
    const lastReported = formatFacilityLastReported(facility.updated_at);
    const projectedCases = Math.max(1, risk?.predicted_cases ?? Math.round(facility.ward_risk_score * 10));
    const surgeRisk = toSurgeRisk(facility.ward_risk_level);
    const orsStockPercent =
      surgeRisk === "EXTREME"
        ? Math.max(12, 42 - projectedCases)
        : surgeRisk === "MODERATE"
          ? Math.max(48, 78 - projectedCases)
          : Math.max(84, 96 - projectedCases);
    const staffingRequired = surgeRisk === "EXTREME" ? 15 : surgeRisk === "MODERATE" ? 10 : 6;
    const staffingFilled = Math.max(
      2,
      staffingRequired - (surgeRisk === "EXTREME" ? 3 : surgeRisk === "MODERATE" ? 2 : 0),
    );

    return {
      id: `${facility.id}`,
      facilityId: facility.id,
      facilityName: facility.name,
      facilityType: formatFacilityType(facility),
      wardId: facility.ward,
      wardName: facility.ward_name,
      subCounty: facility.sub_county,
      surgeRisk,
      projectedCases,
      orsStockPercent,
      orsState: toOrsState(orsStockPercent),
      staffingFilled,
      staffingRequired,
      staffingState: staffingFilled < staffingRequired ? "LIMITED" : "OPTIMAL",
      lastReported: lastReported.label,
      lastReportedMinutes: lastReported.minutes,
      freshnessState: lastReported.freshnessState,
    };
  });
}

export function riskTone(risk: FacilityRow["surgeRisk"]) {
  switch (risk) {
    case "EXTREME":
      return "danger" as const;
    case "MODERATE":
      return "warning" as const;
    case "LOW":
    default:
      return "success" as const;
  }
}

export function stockTone(state: FacilityRow["orsState"]) {
  switch (state) {
    case "CRITICAL":
      return "danger" as const;
    case "STABLE":
      return "warning" as const;
    case "READY":
    default:
      return "success" as const;
  }
}

export function staffingTone(state: FacilityRow["staffingState"]) {
  return state === "LIMITED" ? ("warning" as const) : ("success" as const);
}

export function freshnessTone(state: FacilityRow["freshnessState"]) {
  switch (state) {
    case "STALE":
      return "danger" as const;
    case "WARNING":
      return "warning" as const;
    case "FRESH":
    default:
      return "success" as const;
  }
}

export function findFacilityAlerts(row: FacilityRow, alerts: AlertRecord[]) {
  return alerts.filter((alert) => alert.ward === row.wardId);
}
