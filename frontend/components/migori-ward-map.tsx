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

const MAP_CANVAS = "#F8FAFC";
const MAP_GRID = "#CBD5E1";
const SAFE_FILL = "#EEF6F2";
const SAFE_FILL_HOVER = "#E3F1E9";
const SAFE_STROKE = "#CBD5E1";
const WATCH_FILL = "#FFF4E5";
const WATCH_FILL_HOVER = "#FDE9C8";
const WATCH_STROKE = "#F59E0B";
const HIGH_FILL = "#FEE2E2";
const HIGH_FILL_HOVER = "#FBCACA";
const HIGH_STROKE = "#DC2626";
const UNMATCHED_FILL = "#F1F5F9";
const UNMATCHED_FILL_HOVER = "#E2E8F0";
const UNMATCHED_STROKE = "#94A3B8";
const HOVER_STROKE = "#2563EB";
const SELECTED_STROKE = "#1D4ED8";
const SELECTED_FILL = "#DBEAFE";
const COUNTY_OUTLINE = "#334155";

function getRiskPalette(feature: WardMapFeature) {
  if (!feature.properties.has_backend_ward) {
    return {
      fill: UNMATCHED_FILL,
      fillHover: UNMATCHED_FILL_HOVER,
      stroke: UNMATCHED_STROKE,
      glow: SELECTED_FILL,
      dashArray: "4 3",
    };
  }

  if (feature.properties.risk_level === "HIGH") {
    return {
      fill: HIGH_FILL,
      fillHover: HIGH_FILL_HOVER,
      stroke: HIGH_STROKE,
      glow: "#FECACA",
      dashArray: undefined,
    };
  }

  if (feature.properties.risk_level === "MEDIUM") {
    return {
      fill: WATCH_FILL,
      fillHover: WATCH_FILL_HOVER,
      stroke: WATCH_STROKE,
      glow: "#FDE68A",
      dashArray: undefined,
    };
  }

  return {
    fill: SAFE_FILL,
    fillHover: SAFE_FILL_HOVER,
    stroke: SAFE_STROKE,
    glow: "#E0ECFF",
    dashArray: undefined,
  };
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
          const palette = getRiskPalette(feature);

          return (
            <g key={feature.properties.ward_code}>
              <path
                d={geometryToPath(feature, bounds)}
                fill={palette.glow}
                className={cn("transition-opacity duration-200", isMuted ? "opacity-0" : "opacity-100")}
                stroke="none"
                transform={isSelected ? "scale(1.002)" : undefined}
                style={{ transformOrigin: `${centroid[0]}px ${centroid[1]}px` }}
              />
              <path
                d={geometryToPath(feature, bounds)}
                fill={isSelected ? SELECTED_FILL : isHovered ? palette.fillHover : palette.fill}
                stroke={isSelected ? SELECTED_STROKE : isHovered ? HOVER_STROKE : palette.stroke}
                className={cn(
                  "cursor-pointer transition-all duration-200",
                  isMuted ? "opacity-30" : isHovered || isSelected ? "opacity-100" : "opacity-95",
                )}
                strokeWidth={isSelected ? 2.5 : isHovered ? 1.5 : 1}
                strokeDasharray={palette.dashArray}
                vectorEffect="non-scaling-stroke"
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
                  <circle
                    cx={centroid[0]}
                    cy={centroid[1]}
                    r={isSelected ? 7 : 5}
                    fill="#FFFFFF"
                    stroke={isSelected ? SELECTED_STROKE : palette.stroke}
                    strokeWidth={2}
                    className={cn("pointer-events-none", isMuted && "opacity-40")}
                  />
                  <text
                    x={centroid[0]}
                    y={centroid[1] - 14}
                    textAnchor="middle"
                    className={cn("pointer-events-none fill-panel-strong text-[22px] font-semibold", isMuted && "opacity-40")}
                  >
                    {feature.properties.name}
                  </text>
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
          className="pointer-events-none absolute z-20 w-52 rounded-2xl border border-[#CBD5E1] bg-white/95 p-3 text-xs shadow-[0_24px_80px_rgba(15,23,42,0.14)] backdrop-blur"
          style={{
            left: `${hoveredWard.xPercent > 66 ? hoveredWard.xPercent - 26 : hoveredWard.xPercent + 4}%`,
            top: `${hoveredWard.yPercent > 62 ? hoveredWard.yPercent - 28 : hoveredWard.yPercent + 3}%`,
          }}
        >
          <p className="font-semibold text-panel-strong">{hoveredWard.feature.properties.name}</p>
          <p className="mt-1 text-panel-muted">{getRiskLabel(hoveredWard.feature)}</p>
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
