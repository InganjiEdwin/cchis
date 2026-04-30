"use client";

import { useMemo, useState, type MouseEvent } from "react";

import type { WardDecisionConsoleTriggerState, WardMapFeature } from "@/lib/dashboard";

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 560;
const PADDING = 26;

type OverviewHotspotMapProps = {
  features: WardMapFeature[];
  highlightedWardId?: number | null;
  focusedWardId?: number | null;
  readinessSignals?: Array<{
    ward_id: number;
    facility_capacity_signal: "ready" | "watch" | "capacity_concern";
    facility_count: number;
  }>;
  triggerLinkage?: Array<{
    ward_id: number;
    workflow_state: WardDecisionConsoleTriggerState;
    workflow_state_label: string;
    trigger_reason: string;
    trigger_severity: "high" | "medium" | "review";
    alert_delivery_state:
      | "awaiting_review"
      | "triggered_queued"
      | "triggered_delivered"
      | "triggered_retry_pending"
      | "triggered_failed";
    alert_delivery_label: string;
  }>;
  activeFilter?: OverviewMapFilter;
  hoveredFilter?: OverviewMapFilter | null;
  riskMode?: OverviewRiskMode;
  lastUpdatedLabel?: string | null;
  onSelectWard?: (feature: WardMapFeature) => void;
};

export type OverviewMapFilter = "all" | "high" | "medium" | "low" | "alerts" | "workflow_active" | "delivery_concern";
export type OverviewRiskMode = "current" | "predicted";

type Bounds = {
  minLon: number;
  maxLon: number;
  minLat: number;
  maxLat: number;
};

type Projection = Bounds & {
  scale: number;
  offsetX: number;
  offsetY: number;
};

type HoveredWard = {
  feature: WardMapFeature;
  xPercent: number;
  yPercent: number;
};

type TooltipPosition = {
  left: string;
  top: string;
};

type TooltipPlacement = "right-bottom" | "right-top" | "left-bottom" | "left-top";

const MAP_CANVAS = "var(--dashboard-panel-surface)";
const MAP_GRID = "var(--dashboard-table-line)";
const LOW_FILL = "#16A34A";
const MEDIUM_FILL = "#F59E0B";
const HIGH_FILL = "#DC2626";
const LOW_FILL_PREDICTED = "#4ADE80";
const MEDIUM_FILL_PREDICTED = "#FBBF24";
const HIGH_FILL_PREDICTED = "#F87171";
const DEFAULT_FILL = "#94A3B8";
const BORDER = "rgba(255,255,255,0.12)";
const HOVER_BORDER = "#60A5FA";
const SELECTED_BORDER = "#93C5FD";
const ALERT_PULSE_HIGH = "#DC2626";
const ALERT_PULSE_MEDIUM = "#F59E0B";
const ALERT_PULSE_LOW = "#FB923C";
const TOOLTIP_WIDTH_PERCENT = 25.6;
const TOOLTIP_HEIGHT_PERCENT = 34;
const TOOLTIP_MARGIN_PERCENT = 2;
const TOOLTIP_SIDE_OFFSET_PERCENT = 7;
const TOOLTIP_VERTICAL_ANCHOR_OFFSET_PERCENT = 6;

function getFeatureRiskLevel(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  return riskMode === "predicted" ? feature.properties.prediction.predicted_risk_level : feature.properties.current_risk_level;
}

function getFeatureRiskScore(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  return riskMode === "predicted" ? feature.properties.prediction.predicted_risk_score : feature.properties.current_risk_score;
}

function matchesFilterForMode(
  feature: WardMapFeature,
  filter: OverviewMapFilter,
  riskMode: OverviewRiskMode,
  triggerState:
    | {
        alert_delivery_state:
          | "awaiting_review"
          | "triggered_queued"
          | "triggered_delivered"
          | "triggered_retry_pending"
          | "triggered_failed";
      }
    | null,
) {
  const activeLevel = getFeatureRiskLevel(feature, riskMode);
  if (filter === "all") return true;
  if (filter === "alerts") return feature.properties.alert_count > 0;
  if (filter === "workflow_active") return Boolean(triggerState);
  if (filter === "delivery_concern") {
    return (
      triggerState?.alert_delivery_state === "triggered_retry_pending" ||
      triggerState?.alert_delivery_state === "triggered_failed"
    );
  }
  if (filter === "high") return activeLevel === "HIGH";
  if (filter === "medium") return activeLevel === "MEDIUM";
  if (filter === "low") return activeLevel === "LOW";
  return true;
}

function getActionRecommendation(feature: WardMapFeature) {
  if (feature.properties.alert_count > 0) {
    return "Review alerts";
  }

  if ((feature.properties.prediction.predicted_risk_level ?? feature.properties.current_risk_level) === "HIGH") {
    return "Investigate ward";
  }

  if ((feature.properties.prediction.predicted_risk_level ?? feature.properties.current_risk_level) === "MEDIUM") {
    return "Monitor closely";
  }

  return "Continue monitoring";
}

function formatDeliveryStateLabel(
  state:
    | "awaiting_review"
    | "triggered_queued"
    | "triggered_delivered"
    | "triggered_retry_pending"
    | "triggered_failed",
) {
  if (state === "triggered_delivered") return "Delivered";
  if (state === "triggered_retry_pending") return "Retry pending";
  if (state === "triggered_failed") return "Failed";
  if (state === "triggered_queued") return "Queued";
  return "Awaiting review";
}

function getTriggerStatusLabel(
  triggerState:
    | {
        workflow_state_label: string;
      }
    | null,
) {
  if (!triggerState) return "No active trigger";
  return triggerState.workflow_state_label;
}

function getTriggerStatusTone(
  triggerState:
    | {
        workflow_state: WardDecisionConsoleTriggerState;
      }
    | null,
) {
  if (!triggerState) return "bg-panel-table-wrap text-panel-muted";
  if (triggerState.workflow_state === "ACTION_IN_PROGRESS") {
    return "bg-[color:var(--danger)]/15 text-[color:var(--danger)]";
  }
  if (triggerState.workflow_state === "REVIEW_PENDING") {
    return "bg-[color:var(--warning)]/15 text-[color:var(--warning)]";
  }
  if (triggerState.workflow_state === "TRIGGER_ACTIVE" || triggerState.workflow_state === "RESOLVED") {
    return "bg-[color:var(--success)]/15 text-[color:var(--success)]";
  }
  return "bg-[color:var(--warning)]/15 text-[color:var(--warning)]";
}

function getWhyItMattersLabel(
  feature: WardMapFeature,
  riskMode: OverviewRiskMode,
  triggerState:
    | {
        workflow_state: WardDecisionConsoleTriggerState;
      }
    | null,
) {
  if (feature.properties.alert_count > 0) {
    return `${feature.properties.alert_count} active alert${feature.properties.alert_count === 1 ? "" : "s"} require CHV follow-up in this ward`;
  }

  if (triggerState?.workflow_state && triggerState.workflow_state !== "NONE") {
    return "Trigger conditions are active and need review in this ward";
  }

  if (riskMode === "predicted" && feature.properties.prediction.predicted_risk_level === "HIGH") {
    return "Predicted risk remains elevated for this ward over the next 7 days";
  }

  if (feature.properties.current_risk_level === "HIGH") {
    return "This ward remains in the current high-risk band";
  }

  return "No urgent trigger condition is visible in this ward right now";
}

function formatFacilityReadinessLabel(signal: "ready" | "watch" | "capacity_concern" | null) {
  if (signal === "capacity_concern") return "Capacity concern";
  if (signal === "watch") return "Watch";
  return "OK";
}

function getMarkerPriorityScore(feature: WardMapFeature) {
  const level = feature.properties.prediction.predicted_risk_level ?? feature.properties.current_risk_level;
  const riskWeight = level === "HIGH" ? 3 : level === "MEDIUM" ? 2 : 1;
  return riskWeight * 2 + Math.min(feature.properties.alert_count, 3);
}

function getMarkerTone(feature: WardMapFeature) {
  const level = feature.properties.prediction.predicted_risk_level ?? feature.properties.current_risk_level;
  if (level === "HIGH") return ALERT_PULSE_HIGH;
  if (level === "MEDIUM") return ALERT_PULSE_MEDIUM;
  return ALERT_PULSE_LOW;
}

function flattenCoordinates(feature: WardMapFeature): Array<[number, number]> {
  if (feature.geometry.type === "Polygon") {
    return feature.geometry.coordinates.flat() as Array<[number, number]>;
  }

  return feature.geometry.coordinates.flat(2) as Array<[number, number]>;
}

function getBounds(features: WardMapFeature[]): Bounds {
  const coordinates = features.flatMap(flattenCoordinates);
  const lons = coordinates.map(([lon]) => lon);
  const lats = coordinates.map(([, lat]) => lat);

  return {
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
  };
}

function buildProjection(bounds: Bounds): Projection {
  const safeLonSpan = Math.max(bounds.maxLon - bounds.minLon, 0.0001);
  const safeLatSpan = Math.max(bounds.maxLat - bounds.minLat, 0.0001);
  const drawableWidth = VIEWBOX_WIDTH - PADDING * 2;
  const drawableHeight = VIEWBOX_HEIGHT - PADDING * 2;
  const scale = Math.min(drawableWidth / safeLonSpan, drawableHeight / safeLatSpan);
  const renderedWidth = safeLonSpan * scale;
  const renderedHeight = safeLatSpan * scale;

  return {
    ...bounds,
    scale,
    offsetX: PADDING + (drawableWidth - renderedWidth) / 2,
    offsetY: PADDING + (drawableHeight - renderedHeight) / 2,
  };
}

function projectPoint([lon, lat]: [number, number], projection: Projection): [number, number] {
  const x = projection.offsetX + (lon - projection.minLon) * projection.scale;
  const y = VIEWBOX_HEIGHT - projection.offsetY - (lat - projection.minLat) * projection.scale;
  return [x, y];
}

function polygonRingToPath(ring: number[][], projection: Projection) {
  return ring
    .map((point, index) => {
      const [x, y] = projectPoint(point as [number, number], projection);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function geometryToPath(feature: WardMapFeature, projection: Projection) {
  if (feature.geometry.type === "Polygon") {
    return `${(feature.geometry.coordinates as number[][][]).map((ring) => `${polygonRingToPath(ring, projection)} Z`).join(" ")}`;
  }

  return (feature.geometry.coordinates as number[][][][])
    .map((polygon) => polygon.map((ring) => `${polygonRingToPath(ring, projection)} Z`).join(" "))
    .join(" ");
}

function getRiskFill(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  const level = getFeatureRiskLevel(feature, riskMode);
  if (level === "HIGH") return riskMode === "predicted" ? HIGH_FILL_PREDICTED : HIGH_FILL;
  if (level === "MEDIUM") return riskMode === "predicted" ? MEDIUM_FILL_PREDICTED : MEDIUM_FILL;
  if (level === "LOW") return riskMode === "predicted" ? LOW_FILL_PREDICTED : LOW_FILL;
  return DEFAULT_FILL;
}

function getRiskLabel(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  const level = getFeatureRiskLevel(feature, riskMode);
  if (level === "HIGH") return "High";
  if (level === "MEDIUM") return "Medium";
  if (level === "LOW") return "Low";
  return "Unknown";
}

function getWardAnchor(feature: WardMapFeature, projection: Projection): HoveredWard {
  const [x, y] = feature.properties.centroid
    ? projectPoint(feature.properties.centroid, projection)
    : projectPoint(flattenCoordinates(feature)[0], projection);

  return {
    feature,
    xPercent: (x / VIEWBOX_WIDTH) * 100,
    yPercent: (y / VIEWBOX_HEIGHT) * 100,
  };
}

function getHoverAnchor(event: MouseEvent<SVGPathElement>, feature: WardMapFeature): HoveredWard {
  const svg = event.currentTarget.ownerSVGElement;
  if (!svg) {
    return { feature, xPercent: 50, yPercent: 50 };
  }

  const rect = svg.getBoundingClientRect();
  return {
    feature,
    xPercent: ((event.clientX - rect.left) / rect.width) * 100,
    yPercent: ((event.clientY - rect.top) / rect.height) * 100,
  };
}

function getTooltipPosition(anchor: HoveredWard, mode: "hover" | "pinned"): TooltipPosition {
  const isBottomRightCorner = anchor.xPercent >= 68 && anchor.yPercent >= 62;
  const placements: TooltipPlacement[] = isBottomRightCorner
    ? ["left-top", "left-bottom", "right-top", "right-bottom"]
    : mode === "hover"
      ? ["right-bottom", "right-top", "left-bottom", "left-top"]
      : ["right-top", "right-bottom", "left-top", "left-bottom"];

  const candidatePositions = placements.map((placement) => {
    const placeRight = placement.startsWith("right");
    const placeBottom = placement.endsWith("bottom");
    const horizontalOffset =
      isBottomRightCorner && !placeRight ? TOOLTIP_SIDE_OFFSET_PERCENT + 6 : TOOLTIP_SIDE_OFFSET_PERCENT;
    const verticalOffset =
      isBottomRightCorner && !placeBottom ? TOOLTIP_VERTICAL_ANCHOR_OFFSET_PERCENT + 6 : TOOLTIP_VERTICAL_ANCHOR_OFFSET_PERCENT;
    const rawLeft = placeRight
      ? anchor.xPercent + horizontalOffset
      : anchor.xPercent - TOOLTIP_WIDTH_PERCENT - horizontalOffset;
    const rawTop = placeBottom
      ? anchor.yPercent + verticalOffset
      : anchor.yPercent - TOOLTIP_HEIGHT_PERCENT - verticalOffset;
    const overflowLeft = Math.max(0, TOOLTIP_MARGIN_PERCENT - rawLeft);
    const overflowRight = Math.max(0, rawLeft + TOOLTIP_WIDTH_PERCENT - (100 - TOOLTIP_MARGIN_PERCENT));
    const overflowTop = Math.max(0, TOOLTIP_MARGIN_PERCENT - rawTop);
    const overflowBottom = Math.max(0, rawTop + TOOLTIP_HEIGHT_PERCENT - (100 - TOOLTIP_MARGIN_PERCENT));
    const placementPenalty =
      isBottomRightCorner && (placeRight || placeBottom)
        ? (placeRight ? 8 : 0) + (placeBottom ? 8 : 0)
        : 0;
    const totalOverflow = overflowLeft + overflowRight + overflowTop + overflowBottom + placementPenalty;

    return {
      rawLeft,
      rawTop,
      totalOverflow,
    };
  });

  const bestPosition = candidatePositions.reduce((best, current) =>
    current.totalOverflow < best.totalOverflow ? current : best,
  );

  const clampedLeft = Math.min(
    Math.max(bestPosition.rawLeft, TOOLTIP_MARGIN_PERCENT),
    100 - TOOLTIP_WIDTH_PERCENT - TOOLTIP_MARGIN_PERCENT,
  );
  const clampedTop = Math.min(
    Math.max(bestPosition.rawTop, TOOLTIP_MARGIN_PERCENT),
    100 - TOOLTIP_HEIGHT_PERCENT - TOOLTIP_MARGIN_PERCENT,
  );

  return {
    left: `${clampedLeft}%`,
    top: `${clampedTop}%`,
  };
}

export function OverviewHotspotMap({
  features,
  highlightedWardId,
  focusedWardId = null,
  readinessSignals = [],
  triggerLinkage = [],
  activeFilter = "all",
  hoveredFilter = null,
  riskMode = "current",
  lastUpdatedLabel,
  onSelectWard,
}: OverviewHotspotMapProps) {
  const bounds = useMemo(() => getBounds(features), [features]);
  const projection = useMemo(() => buildProjection(bounds), [bounds]);
  const [hoveredWard, setHoveredWard] = useState<HoveredWard | null>(null);
  const [pinnedWard, setPinnedWard] = useState<HoveredWard | null>(null);
  const effectiveFilter = hoveredFilter ?? activeFilter;
  const topAlertPriority = useMemo(
    () =>
      features
        .filter((feature) => feature.properties.alert_count > 0)
        .reduce((highest, feature) => Math.max(highest, getMarkerPriorityScore(feature)), 0),
    [features],
  );
  const readinessSignalMap = useMemo(
    () => new Map(readinessSignals.map((signal) => [signal.ward_id, signal])),
    [readinessSignals],
  );
  const triggerLinkageMap = useMemo(
    () => new Map(triggerLinkage.map((item) => [item.ward_id, item])),
    [triggerLinkage],
  );
  const activeWard = pinnedWard ?? hoveredWard;
  const isTooltipPinned = Boolean(pinnedWard);

  return (
    <div
      className="relative h-full w-full overflow-visible"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          setPinnedWard(null);
          setHoveredWard(null);
        }
      }}
    >
      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="h-full w-full"
        role="img"
        aria-label={riskMode === "predicted" ? "Predicted risk hotspot map" : "Current risk hotspot map"}
        onClick={() => {
          setPinnedWard(null);
          setHoveredWard(null);
        }}
      >
        <defs>
          <filter id="hotspot-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <style>
          {`
            .overview-hotspot-pulse {
              animation: overview-hotspot-pulse 2.6s ease-in-out infinite;
              transform-box: fill-box;
              transform-origin: center;
            }
            .overview-hotspot-ripple {
              animation: overview-hotspot-ripple 2.6s ease-out infinite;
              transform-box: fill-box;
              transform-origin: center;
            }
            @keyframes overview-hotspot-pulse {
              0%, 100% { opacity: 0.92; transform: scale(0.92); }
              50% { opacity: 1; transform: scale(1.14); }
            }
            @keyframes overview-hotspot-ripple {
              0% { opacity: 0.42; transform: scale(0.72); }
              70% { opacity: 0.08; transform: scale(1.28); }
              100% { opacity: 0; transform: scale(1.38); }
            }
          `}
        </style>
        <rect x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} fill={MAP_CANVAS} rx="28" ry="28" />
        <rect
          x="12"
          y="12"
          width={VIEWBOX_WIDTH - 24}
          height={VIEWBOX_HEIGHT - 24}
          fill="none"
          rx="24"
          ry="24"
          stroke="var(--dashboard-table-line)"
          strokeWidth="1"
          opacity="0.65"
        />
        <g className="pointer-events-none opacity-[0.08]">
          {Array.from({ length: 16 }).map((_, index) => (
            <line
              key={`vertical-${index}`}
              x1={index * 72}
              y1="0"
              x2={index * 72}
              y2={VIEWBOX_HEIGHT}
              stroke={MAP_GRID}
              strokeWidth="1"
            />
          ))}
          {Array.from({ length: 10 }).map((_, index) => (
            <line
              key={`horizontal-${index}`}
              x1="0"
              y1={index * 60}
              x2={VIEWBOX_WIDTH}
              y2={index * 60}
              stroke={MAP_GRID}
              strokeWidth="1"
            />
          ))}
        </g>
        <text
          x="34"
          y="48"
          fill="var(--dashboard-subtle-copy)"
          fontSize="18"
          fontWeight="600"
          letterSpacing="0.08em"
          opacity="0.82"
        >
          MIGORI COUNTY
        </text>
        <text
          x="34"
          y="72"
          fill="var(--dashboard-subtle-copy)"
          fontSize="13"
          fontWeight="600"
          letterSpacing="0.08em"
          opacity="0.76"
        >
          {riskMode === "predicted" ? "PREDICTED MODE (7D)" : "CURRENT MODE"}
        </text>
        {lastUpdatedLabel ? (
          <text
            x={VIEWBOX_WIDTH - 34}
            y="48"
            fill="var(--dashboard-subtle-copy)"
            fontSize="14"
            fontWeight="500"
            textAnchor="end"
            opacity="0.78"
          >
            Updated {lastUpdatedLabel}
          </text>
        ) : null}
        {features.map((feature) => {
          const isHovered = hoveredWard?.feature.properties.ward_code === feature.properties.ward_code;
          const isHighlighted = highlightedWardId === feature.properties.backend_ward_id;
          const isFocused = focusedWardId === feature.properties.backend_ward_id;
          const triggerState = feature.properties.backend_ward_id
            ? triggerLinkageMap.get(feature.properties.backend_ward_id) ?? null
            : null;
          const matchesActiveFilter = matchesFilterForMode(feature, effectiveFilter, riskMode, triggerState);
          const path = geometryToPath(feature, projection);
          const centroid = feature.properties.centroid
            ? projectPoint(feature.properties.centroid, projection)
            : projectPoint(flattenCoordinates(feature)[0], projection);
          const activeAlerts = feature.properties.alert_count;
          const markerPriority = getMarkerPriorityScore(feature);
          const isTopPriority = activeAlerts > 0 && markerPriority === topAlertPriority;
          const markerTone = getMarkerTone(feature);
          const riskLevel = getFeatureRiskLevel(feature, riskMode);
          const markerRadius = isTopPriority ? 6.2 : riskLevel === "MEDIUM" ? 5.2 : 4.4;
          const readinessSignal = feature.properties.backend_ward_id
            ? readinessSignalMap.get(feature.properties.backend_ward_id) ?? null
            : null;
          const readinessTone =
            readinessSignal?.facility_capacity_signal === "capacity_concern"
              ? HIGH_FILL
              : readinessSignal?.facility_capacity_signal === "watch"
                ? MEDIUM_FILL
                : LOW_FILL;
          const hasDeliveryConcern =
            triggerState?.alert_delivery_state === "triggered_retry_pending" ||
            triggerState?.alert_delivery_state === "triggered_failed";

          return (
            <g key={feature.properties.ward_code}>
              <path
                d={path}
                fill={getRiskFill(feature, riskMode)}
                opacity={
                  !matchesActiveFilter
                    ? 0.08
                    : isHighlighted
                      ? 0.92
                      : isFocused
                        ? 0.84
                        : isHovered
                          ? 0.78
                          : focusedWardId
                            ? 0.26
                            : riskMode === "predicted"
                              ? 0.58
                              : 0.66
                }
                stroke={isHighlighted ? SELECTED_BORDER : isFocused ? HOVER_BORDER : isHovered ? HOVER_BORDER : BORDER}
                strokeWidth={isHighlighted ? 2.4 : isFocused ? 1.8 : isHovered ? 1.4 : 0.9}
                vectorEffect="non-scaling-stroke"
                className="cursor-pointer transition-all duration-200"
                onClick={(event) => {
                  event.stopPropagation();
                  const anchor = getWardAnchor(feature, projection);
                  setPinnedWard((current) =>
                    current?.feature.properties.ward_code === feature.properties.ward_code ? null : anchor,
                  );
                  setHoveredWard(anchor);
                  onSelectWard?.(feature);
                }}
                onMouseLeave={() => {
                  if (pinnedWard) return;
                  setHoveredWard((current) =>
                    current?.feature.properties.ward_code === feature.properties.ward_code ? null : current,
                  );
                }}
                onMouseMove={(event) => {
                  if (pinnedWard) return;
                  setHoveredWard(getHoverAnchor(event, feature));
                }}
              />
              {activeAlerts > 0 ? (
                <>
                  {isTopPriority || isFocused ? (
                    <circle
                      cx={centroid[0]}
                      cy={centroid[1]}
                      r="18"
                      fill={markerTone}
                      opacity={matchesActiveFilter ? (isFocused ? "0.34" : "0.28") : "0.12"}
                      className="overview-hotspot-ripple pointer-events-none"
                      filter="url(#hotspot-glow)"
                    />
                  ) : null}
                  <circle
                    cx={centroid[0]}
                    cy={centroid[1]}
                    r={markerRadius}
                    fill={markerTone}
                    stroke="#FFF7ED"
                    strokeWidth="1.5"
                    opacity={matchesActiveFilter ? (focusedWardId && !isFocused ? "0.36" : "1") : "0.28"}
                    className={`pointer-events-none transition-opacity duration-200 ${isTopPriority || isFocused ? "overview-hotspot-pulse" : ""}`}
                  />
                </>
              ) : null}
              {hasDeliveryConcern ? (
                <g className="pointer-events-none">
                  <circle
                    cx={centroid[0] + 13}
                    cy={centroid[1] - 12}
                    r="6.2"
                    fill={triggerState?.alert_delivery_state === "triggered_failed" ? HIGH_FILL : MEDIUM_FILL}
                    stroke="#FFF7ED"
                    strokeWidth="1.4"
                    opacity={focusedWardId && !isFocused ? 0.34 : 0.95}
                  />
                </g>
              ) : null}
              {readinessSignal && readinessSignal.facility_capacity_signal !== "ready" ? (
                <g className="pointer-events-none">
                  <rect
                    x={centroid[0] - 5}
                    y={centroid[1] + 10}
                    width="10"
                    height="10"
                    fill={readinessTone}
                    stroke="#FFF7ED"
                    strokeWidth="1.4"
                    transform={`rotate(45 ${centroid[0]} ${centroid[1] + 15})`}
                    opacity={focusedWardId && !isFocused ? 0.32 : 0.92}
                  />
                </g>
              ) : null}
            </g>
          );
        })}
      </svg>

      {activeWard ? (
        (() => {
          const triggerState = activeWard.feature.properties.backend_ward_id
            ? triggerLinkageMap.get(activeWard.feature.properties.backend_ward_id) ?? null
            : null;
          const readinessSignal = activeWard.feature.properties.backend_ward_id
            ? readinessSignalMap.get(activeWard.feature.properties.backend_ward_id) ?? null
            : null;
          const actionLabel = getActionRecommendation(activeWard.feature);
          const deliveryLabel = activeWard.feature.properties.backend_ward_id
            ? formatDeliveryStateLabel(
                triggerLinkageMap.get(activeWard.feature.properties.backend_ward_id)?.alert_delivery_state ?? "awaiting_review",
              )
            : "Awaiting review";
          const tooltipPosition = getTooltipPosition(activeWard, isTooltipPinned ? "pinned" : "hover");

          return (
            <div
              className={`absolute z-50 w-64 rounded-2xl border border-panel-table-wrap bg-panel/95 p-3 text-xs shadow-[0_24px_80px_rgba(15,23,42,0.24)] backdrop-blur ${
                isTooltipPinned ? "pointer-events-auto" : "pointer-events-none"
              }`}
              style={tooltipPosition}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-panel-strong">{activeWard.feature.properties.name}</p>
                <span className="rounded-full border border-panel-table-wrap px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-panel-strong">
                  {getRiskLabel(activeWard.feature, riskMode)}
                </span>
              </div>

              <div className="mt-3 space-y-3">
                <div className="space-y-1">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-panel-muted">Trigger status</p>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${getTriggerStatusTone(triggerState)}`}
                  >
                    {getTriggerStatusLabel(triggerState)}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 rounded-[1rem] border border-panel-table-wrap/80 bg-panel/60 px-3 py-3">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-panel-muted">Alerts</p>
                    <p className="mt-1 text-sm font-semibold text-panel-strong">
                      {activeWard.feature.properties.alert_count} active
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-panel-muted">Alert delivery</p>
                    <p className="mt-1 text-sm font-semibold text-panel-strong">{deliveryLabel}</p>
                  </div>
                </div>

                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-panel-muted">Why it matters</p>
                  <p className="mt-1 text-sm text-panel-copy">
                    {getWhyItMattersLabel(activeWard.feature, riskMode, triggerState)}
                  </p>
                </div>

                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-panel-muted">Recommended action</p>
                  <p className="mt-1 text-sm font-semibold text-panel-strong">{actionLabel}</p>
                </div>

                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-panel-muted">
                    Facility readiness: {formatFacilityReadinessLabel(readinessSignal?.facility_capacity_signal ?? null)}
                  </span>
                  {isTooltipPinned ? (
                    <button
                      type="button"
                      className="inline-flex items-center justify-center rounded-pill border border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-3 py-1.5 text-[11px] font-semibold text-brand transition hover:bg-[color-mix(in_srgb,var(--brand)_16%,white)]"
                      onClick={() => {
                        setPinnedWard(getWardAnchor(activeWard.feature, projection));
                        setHoveredWard(getWardAnchor(activeWard.feature, projection));
                        onSelectWard?.(activeWard.feature);
                      }}
                    >
                      Open ward focus
                    </button>
                  ) : (
                    <span className="rounded-pill border border-panel-table-wrap px-3 py-1.5 text-[11px] font-semibold text-panel-muted">
                      Click ward to pin
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })()
      ) : null}
    </div>
  );
}
