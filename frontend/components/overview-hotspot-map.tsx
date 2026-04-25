"use client";

import { useMemo, useState } from "react";

import type { WardMapFeature } from "@/lib/dashboard";

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 560;
const PADDING = 26;

type OverviewHotspotMapProps = {
  features: WardMapFeature[];
  highlightedWardId?: number | null;
  activeFilter?: OverviewMapFilter;
  hoveredFilter?: OverviewMapFilter | null;
  lastUpdatedLabel?: string | null;
  onSelectWard?: (feature: WardMapFeature) => void;
};

export type OverviewMapFilter = "all" | "high" | "medium" | "low" | "alerts";

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

const MAP_CANVAS = "var(--dashboard-panel-surface)";
const MAP_GRID = "var(--dashboard-table-line)";
const LOW_FILL = "#16A34A";
const MEDIUM_FILL = "#F59E0B";
const HIGH_FILL = "#DC2626";
const DEFAULT_FILL = "#94A3B8";
const BORDER = "rgba(255,255,255,0.12)";
const HOVER_BORDER = "#60A5FA";
const SELECTED_BORDER = "#93C5FD";
const ALERT_PULSE_HIGH = "#DC2626";
const ALERT_PULSE_MEDIUM = "#F59E0B";
const ALERT_PULSE_LOW = "#FB923C";

function matchesFilter(feature: WardMapFeature, filter: OverviewMapFilter) {
  if (filter === "all") return true;
  if (filter === "alerts") return feature.properties.alert_count > 0;
  if (filter === "high") return feature.properties.risk_level === "HIGH";
  if (filter === "medium") return feature.properties.risk_level === "MEDIUM";
  if (filter === "low") return feature.properties.risk_level === "LOW";
  return true;
}

function getActionRecommendation(feature: WardMapFeature) {
  if (feature.properties.alert_count > 0) {
    return "Review alerts";
  }

  if (feature.properties.risk_level === "HIGH") {
    return "Investigate ward";
  }

  if (feature.properties.risk_level === "MEDIUM") {
    return "Monitor closely";
  }

  return "Continue monitoring";
}

function getMarkerPriorityScore(feature: WardMapFeature) {
  const riskWeight =
    feature.properties.risk_level === "HIGH" ? 3 : feature.properties.risk_level === "MEDIUM" ? 2 : 1;
  return riskWeight * 2 + Math.min(feature.properties.alert_count, 3);
}

function getMarkerTone(feature: WardMapFeature) {
  if (feature.properties.risk_level === "HIGH") return ALERT_PULSE_HIGH;
  if (feature.properties.risk_level === "MEDIUM") return ALERT_PULSE_MEDIUM;
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
  const y =
    VIEWBOX_HEIGHT -
    projection.offsetY -
    (lat - projection.minLat) * projection.scale;
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

function getRiskFill(feature: WardMapFeature) {
  if (feature.properties.risk_level === "HIGH") return HIGH_FILL;
  if (feature.properties.risk_level === "MEDIUM") return MEDIUM_FILL;
  if (feature.properties.risk_level === "LOW") return LOW_FILL;
  return DEFAULT_FILL;
}

function getRiskLabel(feature: WardMapFeature) {
  if (feature.properties.risk_level === "HIGH") return "High";
  if (feature.properties.risk_level === "MEDIUM") return "Medium";
  if (feature.properties.risk_level === "LOW") return "Low";
  return "Unknown";
}

export function OverviewHotspotMap({
  features,
  highlightedWardId,
  activeFilter = "all",
  hoveredFilter = null,
  lastUpdatedLabel,
  onSelectWard,
}: OverviewHotspotMapProps) {
  const bounds = useMemo(() => getBounds(features), [features]);
  const projection = useMemo(() => buildProjection(bounds), [bounds]);
  const [hoveredWard, setHoveredWard] = useState<HoveredWard | null>(null);
  const effectiveFilter = hoveredFilter ?? activeFilter;
  const topAlertPriority = useMemo(
    () =>
      features
        .filter((feature) => feature.properties.alert_count > 0)
        .reduce((highest, feature) => Math.max(highest, getMarkerPriorityScore(feature)), 0),
    [features],
  );

  return (
    <div className="relative h-full w-full">
      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="h-full w-full"
        role="img"
        aria-label="Live risk hotspot map"
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
          const matchesActiveFilter = matchesFilter(feature, effectiveFilter);
          const path = geometryToPath(feature, projection);
          const centroid = feature.properties.centroid
            ? projectPoint(feature.properties.centroid, projection)
            : projectPoint(flattenCoordinates(feature)[0], projection);
          const activeAlerts = feature.properties.alert_count;
          const markerPriority = getMarkerPriorityScore(feature);
          const isTopPriority = activeAlerts > 0 && markerPriority === topAlertPriority;
          const markerTone = getMarkerTone(feature);
          const markerRadius = isTopPriority ? 6.2 : feature.properties.risk_level === "MEDIUM" ? 5.2 : 4.4;

          return (
            <g key={feature.properties.ward_code}>
              <path
                d={path}
                fill={getRiskFill(feature)}
                opacity={
                  !matchesActiveFilter ? 0.14 : isHighlighted ? 0.86 : isHovered ? 0.78 : 0.66
                }
                stroke={isHighlighted ? SELECTED_BORDER : isHovered ? HOVER_BORDER : BORDER}
                strokeWidth={isHighlighted ? 2.2 : isHovered ? 1.4 : 0.9}
                vectorEffect="non-scaling-stroke"
                className="cursor-pointer transition-all duration-200"
                onClick={() => onSelectWard?.(feature)}
                onMouseLeave={() =>
                  setHoveredWard((current) =>
                    current?.feature.properties.ward_code === feature.properties.ward_code ? null : current,
                  )
                }
                onMouseMove={(event) => {
                  const svg = event.currentTarget.ownerSVGElement;
                  if (!svg) return;
                  const rect = svg.getBoundingClientRect();
                  setHoveredWard({
                    feature,
                    xPercent: ((event.clientX - rect.left) / rect.width) * 100,
                    yPercent: ((event.clientY - rect.top) / rect.height) * 100,
                  });
                }}
              />
              {activeAlerts > 0 ? (
                <>
                  {isTopPriority ? (
                    <circle
                      cx={centroid[0]}
                      cy={centroid[1]}
                      r="18"
                      fill={markerTone}
                      opacity={matchesActiveFilter ? "0.28" : "0.12"}
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
                    opacity={matchesActiveFilter ? "1" : "0.28"}
                    className={`pointer-events-none transition-opacity duration-200 ${isTopPriority ? "overview-hotspot-pulse" : ""}`}
                  />
                </>
              ) : null}
            </g>
          );
        })}
      </svg>

      {hoveredWard ? (
        <div
          className="pointer-events-none absolute z-20 w-52 rounded-2xl border border-panel-table-wrap bg-panel/95 p-3 text-xs shadow-[0_24px_80px_rgba(15,23,42,0.24)] backdrop-blur"
          style={{
            left: `${hoveredWard.xPercent > 66 ? hoveredWard.xPercent - 26 : hoveredWard.xPercent + 4}%`,
            top: `${hoveredWard.yPercent > 62 ? hoveredWard.yPercent - 30 : hoveredWard.yPercent + 3}%`,
          }}
        >
          <p className="font-semibold text-panel-strong">{hoveredWard.feature.properties.name}</p>
          <p className="mt-1 text-panel-muted">{getRiskLabel(hoveredWard.feature)} risk</p>
          <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-panel-copy">
            <span>Alerts</span>
            <strong className="text-right text-panel-strong">{hoveredWard.feature.properties.alert_count}</strong>
            <span>Trend</span>
            <strong className="text-right text-panel-strong">
              {hoveredWard.feature.properties.trend.label}
            </strong>
            <span>Action</span>
            <strong className="text-right text-panel-strong">
              {getActionRecommendation(hoveredWard.feature)}
            </strong>
          </div>
        </div>
      ) : null}
    </div>
  );
}
