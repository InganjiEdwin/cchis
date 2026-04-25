"use client";

import { useMemo, useState } from "react";

import type { WardMapFeature } from "@/lib/dashboard";
import { cn } from "@/lib/cn";

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 760;
const PADDING = 48;

type MigoriWardMapProps = {
  features: WardMapFeature[];
  selectedWardCode?: string | null;
  focusHighRisk?: boolean;
  onSelectWard?: (feature: WardMapFeature) => void;
};

type Bounds = {
  minLon: number;
  maxLon: number;
  minLat: number;
  maxLat: number;
};

type HoveredWard = {
  feature: WardMapFeature;
  xPercent: number;
  yPercent: number;
};

const MAP_CANVAS = "var(--dashboard-panel-surface)";
const MAP_GRID = "var(--dashboard-table-line)";
const GOOD_FILL = "#EEF6F2";
const GOOD_FILL_HOVER = "#E3F4EA";
const LOW_FILL = "#FFF4E5";
const LOW_FILL_HOVER = "#FDE8C8";
const GAP_FILL = "#FEE2E2";
const GAP_FILL_HOVER = "#FCD0D0";
const UNMATCHED_FILL = "#F1F5F9";
const UNMATCHED_FILL_HOVER = "#E2E8F0";
const DEFAULT_STROKE = "#E2E8F0";
const UNMATCHED_STROKE = "var(--dashboard-subtle-copy)";
const HOVER_STROKE = "#2563EB";
const SELECTED_STROKE = "#2563EB";
const SELECTED_FILL = "#DBEAFE";
const COUNTY_OUTLINE = "var(--dashboard-copy)";
const LOW_STROKE = "#F59E0B";
const GAP_STROKE = "#DC2626";

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

function projectPoint([lon, lat]: [number, number], bounds: Bounds): [number, number] {
  const safeLonSpan = Math.max(bounds.maxLon - bounds.minLon, 0.0001);
  const safeLatSpan = Math.max(bounds.maxLat - bounds.minLat, 0.0001);
  const x = PADDING + ((lon - bounds.minLon) / safeLonSpan) * (VIEWBOX_WIDTH - PADDING * 2);
  const y = VIEWBOX_HEIGHT - PADDING - ((lat - bounds.minLat) / safeLatSpan) * (VIEWBOX_HEIGHT - PADDING * 2);
  return [x, y];
}

function polygonRingToPath(ring: number[][], bounds: Bounds) {
  return ring
    .map((point, index) => {
      const [x, y] = projectPoint(point as [number, number], bounds);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function geometryToPath(feature: WardMapFeature, bounds: Bounds) {
  if (feature.geometry.type === "Polygon") {
    return `${(feature.geometry.coordinates as number[][][]).map((ring) => `${polygonRingToPath(ring, bounds)} Z`).join(" ")}`;
  }

  return (feature.geometry.coordinates as number[][][][])
    .map((polygon) => polygon.map((ring) => `${polygonRingToPath(ring, bounds)} Z`).join(" "))
    .join(" ");
}

function getRiskLabel(feature: WardMapFeature) {
  if (!feature.properties.has_backend_ward) {
    return "Unmatched source";
  }

  if (feature.properties.risk_level === "HIGH") {
    return "High risk";
  }

  if (feature.properties.risk_level === "MEDIUM") {
    return "Watch";
  }

  return "Safe";
}

function getCoverageStatus(feature: WardMapFeature) {
  if (!feature.properties.has_backend_ward) {
    return {
      label: "No data",
      tone: "unmatched" as const,
    };
  }

  const active = feature.properties.active_chv_count;
  const total = feature.properties.chv_count;
  const riskLevel = feature.properties.risk_level;

  if (active === 0) {
    return {
      label: "Gap",
      tone: "gap" as const,
    };
  }

  if (riskLevel === "HIGH" && active <= 1) {
    return {
      label: "Gap",
      tone: "gap" as const,
    };
  }

  if ((riskLevel === "HIGH" && active <= 2) || (riskLevel === "MEDIUM" && active <= 1)) {
    return {
      label: "Low",
      tone: "low" as const,
    };
  }

  if (total > 0 && active / total < 0.5) {
    return {
      label: "Low",
      tone: "low" as const,
    };
  }

  return {
    label: "Good",
    tone: "good" as const,
  };
}

function getCoveragePalette(feature: WardMapFeature) {
  const coverageStatus = getCoverageStatus(feature);

  if (coverageStatus.tone === "unmatched") {
    return {
      fill: UNMATCHED_FILL,
      fillHover: UNMATCHED_FILL_HOVER,
      stroke: UNMATCHED_STROKE,
      accentStroke: UNMATCHED_STROKE,
      dashArray: "4 3",
      borderWidth: 1,
      accentWidth: 0,
      accentOpacity: 0,
    };
  }

  if (coverageStatus.tone === "gap") {
    return {
      fill: GAP_FILL,
      fillHover: GAP_FILL_HOVER,
      stroke: DEFAULT_STROKE,
      accentStroke: GAP_STROKE,
      dashArray: undefined,
      borderWidth: 1,
      accentWidth: 2.2,
      accentOpacity: 0.92,
    };
  }

  if (coverageStatus.tone === "low") {
    return {
      fill: LOW_FILL,
      fillHover: LOW_FILL_HOVER,
      stroke: DEFAULT_STROKE,
      accentStroke: LOW_STROKE,
      dashArray: undefined,
      borderWidth: 1,
      accentWidth: 1.2,
      accentOpacity: 0.82,
    };
  }

  return {
    fill: GOOD_FILL,
    fillHover: GOOD_FILL_HOVER,
    stroke: DEFAULT_STROKE,
    accentStroke: "#22C55E",
    dashArray: undefined,
    borderWidth: 1,
    accentWidth: 0,
    accentOpacity: 0,
  };
}

export function MigoriWardMap({
  features,
  selectedWardCode,
  focusHighRisk = false,
  onSelectWard,
}: MigoriWardMapProps) {
  const bounds = useMemo(() => getBounds(features), [features]);
  const [hoveredWard, setHoveredWard] = useState<HoveredWard | null>(null);

  return (
    <div className="relative h-full w-full">
      <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} className="h-full w-full" role="img" aria-label="Migori ward map">
        <rect x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} fill={MAP_CANVAS} rx="28" ry="28" />
        <g className="pointer-events-none opacity-[0.15]">
          {Array.from({ length: 12 }).map((_, index) => (
            <line
              key={`vertical-${index}`}
              x1={index * 84}
              y1="0"
              x2={index * 84}
              y2={VIEWBOX_HEIGHT}
              stroke={MAP_GRID}
              strokeWidth="1"
            />
          ))}
          {Array.from({ length: 10 }).map((_, index) => (
            <line
              key={`horizontal-${index}`}
              x1="0"
              y1={index * 84}
              x2={VIEWBOX_WIDTH}
              y2={index * 84}
              stroke={MAP_GRID}
              strokeWidth="1"
            />
          ))}
        </g>
        {features.map((feature) => {
          const isSelected = selectedWardCode === feature.properties.ward_code;
          const isHovered = hoveredWard?.feature.properties.ward_code === feature.properties.ward_code;
          const isMuted = focusHighRisk && feature.properties.risk_level !== "HIGH";
          const centroid = feature.properties.centroid
            ? projectPoint(feature.properties.centroid, bounds)
            : projectPoint(flattenCoordinates(feature)[0], bounds);
          const palette = getCoveragePalette(feature);
          const coverageStatus = getCoverageStatus(feature);
          const selectedFill = isSelected ? SELECTED_FILL : isHovered ? palette.fillHover : palette.fill;
          const interactiveStroke = isSelected ? SELECTED_STROKE : isHovered ? HOVER_STROKE : palette.stroke;
          const interactiveStrokeWidth = isSelected ? 3 : isHovered ? 1.5 : palette.borderWidth;

          return (
            <g key={feature.properties.ward_code}>
              <path
                d={geometryToPath(feature, bounds)}
                fill={selectedFill}
                stroke={interactiveStroke}
                className={cn(
                  "cursor-pointer transition-all duration-200",
                  isMuted ? "opacity-30" : isHovered || isSelected ? "opacity-100" : "opacity-95",
                )}
                strokeWidth={interactiveStrokeWidth}
                strokeDasharray={palette.dashArray}
                vectorEffect="non-scaling-stroke"
                style={isSelected ? { filter: "drop-shadow(0 0 8px rgba(37,99,235,0.18))" } : undefined}
                onClick={() => onSelectWard?.(feature)}
                onMouseLeave={() => setHoveredWard((current) => (current?.feature.properties.ward_code === feature.properties.ward_code ? null : current))}
                onMouseMove={(event) => {
                  const svg = event.currentTarget.ownerSVGElement;
                  if (!svg) {
                    return;
                  }

                  const rect = svg.getBoundingClientRect();
                  setHoveredWard({
                    feature,
                    xPercent: ((event.clientX - rect.left) / rect.width) * 100,
                    yPercent: ((event.clientY - rect.top) / rect.height) * 100,
                  });
                }}
              />
              {palette.accentWidth > 0 ? (
                <path
                  d={geometryToPath(feature, bounds)}
                  fill="none"
                  stroke={palette.accentStroke}
                  strokeWidth={isSelected ? palette.accentWidth + 0.25 : isHovered ? palette.accentWidth + 0.2 : palette.accentWidth}
                  vectorEffect="non-scaling-stroke"
                  className={cn(
                    "pointer-events-none transition-opacity duration-200",
                    isMuted ? "opacity-25" : "",
                  )}
                  opacity={isSelected ? 0.95 : isHovered ? Math.min(1, palette.accentOpacity + 0.08) : palette.accentOpacity}
                />
              ) : null}
              {isSelected ? (
                <path
                  d={geometryToPath(feature, bounds)}
                  fill="none"
                  stroke={SELECTED_STROKE}
                  strokeWidth={4}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                  className="pointer-events-none opacity-85"
                />
              ) : null}
              {isSelected || isHovered ? (
                <>
                  <text
                    x={centroid[0]}
                    y={centroid[1] - 14}
                    textAnchor="middle"
                    className={cn("pointer-events-none fill-panel-strong text-[22px] font-semibold", isMuted && "opacity-40")}
                  >
                    {feature.properties.name}
                  </text>
                  {isSelected ? (
                    <text
                      x={centroid[0]}
                      y={centroid[1] + 18}
                      textAnchor="middle"
                      className={cn(
                        "pointer-events-none text-[15px] font-semibold",
                        isMuted ? "opacity-40" : "",
                      )}
                      fill={coverageStatus.tone === "gap" ? GAP_STROKE : coverageStatus.tone === "low" ? LOW_STROKE : "#64748B"}
                    >
                      {coverageStatus.label} coverage
                    </text>
                  ) : null}
                </>
              ) : null}
            </g>
          );
        })}
        <rect
          x={PADDING - 6}
          y={PADDING - 6}
          width={VIEWBOX_WIDTH - (PADDING - 6) * 2}
          height={VIEWBOX_HEIGHT - (PADDING - 6) * 2}
          fill="none"
          stroke={COUNTY_OUTLINE}
          strokeWidth="1.5"
          opacity="0.18"
          rx="20"
          ry="20"
          className="pointer-events-none"
        />
      </svg>

      {hoveredWard ? (
        <div
          className="pointer-events-none absolute z-20 w-52 rounded-2xl border border-panel-table-wrap bg-panel/95 p-3 text-xs shadow-[0_24px_80px_rgba(15,23,42,0.24)] backdrop-blur"
          style={{
            left: `${hoveredWard.xPercent > 66 ? hoveredWard.xPercent - 26 : hoveredWard.xPercent + 4}%`,
            top: `${hoveredWard.yPercent > 62 ? hoveredWard.yPercent - 28 : hoveredWard.yPercent + 3}%`,
          }}
        >
          <p className="font-semibold text-panel-strong">{hoveredWard.feature.properties.name}</p>
          <p
            className="mt-1 text-[11px] font-semibold uppercase tracking-[0.16em]"
            style={{
              color:
                getCoverageStatus(hoveredWard.feature).tone === "gap"
                  ? GAP_STROKE
                  : getCoverageStatus(hoveredWard.feature).tone === "low"
                    ? LOW_STROKE
                    : "var(--dashboard-muted-copy)",
            }}
          >
            Coverage {getCoverageStatus(hoveredWard.feature).label}
          </p>
          <p className="mt-1 text-panel-muted">{getRiskLabel(hoveredWard.feature)} risk</p>
          <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-panel-copy">
            <span>Active CHVs</span>
            <strong className="text-right text-panel-strong">{hoveredWard.feature.properties.active_chv_count}</strong>
            <span>Open alerts</span>
            <strong className="text-right text-panel-strong">{hoveredWard.feature.properties.alert_count}</strong>
            <span>Facilities</span>
            <strong className="text-right text-panel-strong">{hoveredWard.feature.properties.facility_count}</strong>
          </div>
        </div>
      ) : null}
    </div>
  );
}
