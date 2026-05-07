from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.utils import timezone

from risk.population_exposure_ingestion import adapter_spec_for_source_type
from risk.source_data.phase0 import (
    FEED_SCOPE_MVP,
    INGESTION_FAMILY_FACILITY_READINESS,
    INGESTION_FAMILY_POPULATION_EXPOSURE,
    INGESTION_FAMILY_SURVEILLANCE,
    SOURCE_DATA_OPS_SCHEMA_VERSION,
    SourceDataFeedDecision,
    mvp_feed_decisions,
)
from risk.surveillance_ingestion import (
    adapter_spec_for_surveillance_source_type,
    feed_policy_for_surveillance_source_type,
)
from risk.source_data.connectors import source_data_connector_state_for_feed


SOURCE_DATA_FEED_REGISTRY_SCHEMA_VERSION = "source-data-feed-registry-v1"


@dataclass(frozen=True)
class SourceDataFeedDefinition:
    feed_key: str
    label: str
    scope: str
    domain: str
    backend_target: str
    source_type: str
    cadence: str
    ingestion_family: str
    downstream_action: str
    required_metadata: tuple[str, ...]
    adapter_key: str
    adapter_notes: str
    scheduled_supported: bool
    required_any_columns: tuple[tuple[str, ...], ...]
    accepted_columns: tuple[str, ...]
    template_url: str
    requires_new_ingestion_path: bool = False
    default_reporting_granularity: str = ""
    feed_policy: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_metadata"] = list(self.required_metadata)
        payload["required_any_columns"] = [list(group) for group in self.required_any_columns]
        payload["accepted_columns"] = list(self.accepted_columns)
        payload["feed_policy"] = self.feed_policy or {}
        payload.update(source_data_connector_state_for_feed(self.feed_key))
        return payload


def _groups_for_adapter(required_any_columns: tuple[frozenset[str], ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(sorted(group)) for group in required_any_columns)


def _definition_from_surveillance_decision(decision: SourceDataFeedDecision) -> SourceDataFeedDefinition:
    spec = adapter_spec_for_surveillance_source_type(decision.source_type)
    policy = feed_policy_for_surveillance_source_type(decision.source_type)
    return SourceDataFeedDefinition(
        feed_key=decision.feed_key,
        label=decision.label,
        scope=decision.scope,
        domain=decision.domain,
        backend_target=decision.backend_target,
        source_type=decision.source_type,
        cadence=decision.cadence,
        ingestion_family=decision.ingestion_family,
        downstream_action=decision.downstream_action,
        required_metadata=decision.required_metadata,
        adapter_key=spec.adapter_key,
        adapter_notes=spec.notes,
        scheduled_supported=spec.scheduled_supported,
        required_any_columns=_groups_for_adapter(spec.required_any_columns),
        accepted_columns=tuple(sorted(spec.accepted_columns)),
        template_url=f"/source-data/templates/{decision.feed_key}/",
        requires_new_ingestion_path=decision.requires_new_ingestion_path,
        default_reporting_granularity=spec.default_reporting_granularity,
        feed_policy=policy.as_dict(),
    )


def _definition_from_population_exposure_decision(decision: SourceDataFeedDecision) -> SourceDataFeedDefinition:
    spec = adapter_spec_for_source_type(decision.source_type)
    return SourceDataFeedDefinition(
        feed_key=decision.feed_key,
        label=decision.label,
        scope=decision.scope,
        domain=decision.domain,
        backend_target=decision.backend_target,
        source_type=decision.source_type,
        cadence=decision.cadence,
        ingestion_family=decision.ingestion_family,
        downstream_action=decision.downstream_action,
        required_metadata=decision.required_metadata,
        adapter_key=spec.adapter_key,
        adapter_notes=spec.notes,
        scheduled_supported=spec.scheduled_supported,
        required_any_columns=_groups_for_adapter(spec.required_any_columns),
        accepted_columns=tuple(sorted(spec.accepted_columns)),
        template_url=f"/source-data/templates/{decision.feed_key}/",
        requires_new_ingestion_path=decision.requires_new_ingestion_path,
    )


def _definition_from_readiness_decision(decision: SourceDataFeedDecision) -> SourceDataFeedDefinition:
    return SourceDataFeedDefinition(
        feed_key=decision.feed_key,
        label=decision.label,
        scope=decision.scope,
        domain=decision.domain,
        backend_target=decision.backend_target,
        source_type=decision.source_type,
        cadence=decision.cadence,
        ingestion_family=INGESTION_FAMILY_FACILITY_READINESS,
        downstream_action=decision.downstream_action,
        required_metadata=decision.required_metadata,
        adapter_key="facility_readiness_snapshot_csv",
        adapter_notes=decision.notes,
        scheduled_supported=False,
        required_any_columns=(
            ("facility_code",),
            ("ward_code",),
            ("reported_at",),
        ),
        accepted_columns=(
            "beds_available",
            "chlorine_available",
            "facility_code",
            "facility_name",
            "iv_fluids_available",
            "ors_sachets_available",
            "referral_available",
            "reported_at",
            "service_disruption",
            "source_kind",
            "source_ref",
            "staff_on_duty",
            "stockout_notes",
            "ward_name",
            "ward_code",
            "zinc_available",
        ),
        template_url=f"/source-data/templates/{decision.feed_key}/",
        requires_new_ingestion_path=decision.requires_new_ingestion_path,
    )


def source_data_feed_definition_from_decision(decision: SourceDataFeedDecision) -> SourceDataFeedDefinition:
    if decision.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        return _definition_from_surveillance_decision(decision)
    if decision.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        return _definition_from_population_exposure_decision(decision)
    if decision.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        return _definition_from_readiness_decision(decision)
    raise ValueError(f"Unsupported source-data ingestion family for feed '{decision.feed_key}'.")


def source_data_feed_definitions(scope: str = FEED_SCOPE_MVP) -> tuple[SourceDataFeedDefinition, ...]:
    if scope != FEED_SCOPE_MVP:
        raise ValueError("Only MVP source-data feed definitions are exposed in Phase 1.")
    return tuple(source_data_feed_definition_from_decision(decision) for decision in mvp_feed_decisions())


def source_data_feed_definition(feed_key: str) -> SourceDataFeedDefinition:
    for definition in source_data_feed_definitions():
        if definition.feed_key == feed_key:
            return definition
    raise KeyError(feed_key)


def build_source_data_feed_types_payload() -> dict[str, Any]:
    feeds = [definition.as_dict() for definition in source_data_feed_definitions()]
    return {
        "schema_version": SOURCE_DATA_FEED_REGISTRY_SCHEMA_VERSION,
        "phase_contract_schema_version": SOURCE_DATA_OPS_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "scope": FEED_SCOPE_MVP,
        "feed_count": len(feeds),
        "feeds": feeds,
    }
