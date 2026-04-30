import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverviewHotspotMap } from "@/components/overview-hotspot-map";

describe("OverviewHotspotMap", () => {
  it("uses normalized workflow labels in the tooltip while keeping delivery detail separate", () => {
    const { container } = render(
      <OverviewHotspotMap
        features={[
          {
            type: "Feature",
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [34.6, -0.9],
                  [34.7, -0.9],
                  [34.7, -1.0],
                  [34.6, -1.0],
                  [34.6, -0.9],
                ],
              ],
            },
            properties: {
              name: "North Kamagambo",
              ward_code: "MIG-01",
              backend_public_id: "WRD-001",
              has_backend_ward: true,
              backend_ward_id: 1,
              centroid: [34.65, -0.95],
              current_risk_level: "HIGH",
              current_risk_score: 0.91,
              risk_level: "HIGH",
              risk_score: 0.91,
              alert_count: 1,
              predicted_cases: 8,
              risk_generated_at: "2026-04-25T08:00:00Z",
              trend: { label: "Escalating", direction: "up", delta_points: 8, mode: "derived_from_recent_history" },
              chv_count: 0,
              active_chv_count: 0,
              facility_count: 0,
              prediction: {
                available: true,
                horizon_days: 7,
                predicted_risk_level: "HIGH",
                predicted_risk_score: 0.92,
                predicted_cases: 8,
                prediction_generated_at: "2026-04-25T08:00:00Z",
                prediction_model_version: "v0-demo",
              },
            },
          },
        ]}
        triggerLinkage={[
          {
            ward_id: 1,
            workflow_state: "ACTION_IN_PROGRESS",
            workflow_state_label: "Action in progress",
            trigger_reason: "Triggered and queued for delivery.",
            trigger_severity: "high",
            alert_delivery_state: "triggered_queued",
            alert_delivery_label: "Triggered and queued",
          },
        ]}
        lastUpdatedLabel="5 min ago"
      />,
    );

    const interactivePath = container.querySelector("path.cursor-pointer");
    expect(interactivePath).not.toBeNull();
    fireEvent.click(interactivePath!);

    expect(screen.getByText("Trigger status")).toBeInTheDocument();
    expect(screen.getByText("Action in progress")).toBeInTheDocument();
    expect(screen.getByText("Alert delivery")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.queryByText("Under review")).not.toBeInTheDocument();
  });
});
