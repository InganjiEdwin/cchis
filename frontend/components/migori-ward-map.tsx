"use client";

import { useMemo } from "react";

import type { WardMapFeature } from "@/lib/dashboard";
import { cn } from "@/lib/cn";

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 760;
const PADDING = 48;

type MigoriWardMapProps = {
  features: WardMapFeature[];
  selectedWardName?: string | null;
  focusHighRisk?: boolean;
  onSelectWard?: (wardName: string) => void;
};

type Bounds = {
  minLon: number;
  maxLon: number;
  minLat: number;
  maxLat: number;
};

function getRiskFill(feature: WardMapFeature) {
  if (feature.properties.risk_level === "HIGH") {
    return "color-mix(in_srgb,var(--danger) 72%, white)";
  }
  if (feature.properties.risk_level === "MEDIUM") {
    return "color-mix(in_srgb,var(--warning) 70%, white)";
  }
  if (feature.properties.has_backend_ward) {
    return "color-mix(in_srgb,var(--brand) 56%, white)";
  }
  return "color-mix(in_srgb,var(--panel-muted) 34%, white)";
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

export function MigoriWardMap({
  features,
  selectedWardName,
  focusHighRisk = false,
  onSelectWard,
}: MigoriWardMapProps) {
  const bounds = useMemo(() => getBounds(features), [features]);

  return (
    <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} className="h-full w-full" role="img" aria-label="Migori ward map">
      {features.map((feature) => {
        const isSelected = selectedWardName === feature.properties.name;
        const isMuted = focusHighRisk && feature.properties.risk_level !== "HIGH";
        const centroid = feature.properties.centroid
          ? projectPoint(feature.properties.centroid, bounds)
          : projectPoint(flattenCoordinates(feature)[0], bounds);

        return (
          <g key={feature.properties.ward_code}>
            <path
              d={geometryToPath(feature, bounds)}
              fill={getRiskFill(feature)}
              className={cn(
                "cursor-pointer stroke-white/90 transition-opacity duration-200",
                isMuted ? "opacity-25" : "opacity-95",
              )}
              strokeWidth={isSelected ? 6 : feature.properties.active_chv_count === 0 ? 3.5 : 2.5}
              onClick={() => onSelectWard?.(feature.properties.name)}
            />
            <text
              x={centroid[0]}
              y={centroid[1]}
              textAnchor="middle"
              className={cn(
                "pointer-events-none fill-panel-strong text-[20px] font-semibold",
                isMuted && "opacity-35",
              )}
            >
              {feature.properties.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
