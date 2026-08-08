"""Run two small read-only DHIS2 Play -> CCHIS interoperability proof reads."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.models import InteroperabilityRun, SourceDataConnectorRun, SurveillanceRecord
from risk.source_data.connectors import run_source_data_connector_refresh
from risk.source_data.dhis2 import Dhis2OperatorError, dhis2_api_configured, resolve_dhis2_operator


class Command(BaseCommand):
    help = "Run two narrow, read-only DHIS2 Play aggregate proof reads through CCHIS ingestion."

    def add_arguments(self, parser):
        parser.add_argument(
            "--operator-username",
            required=True,
            help="Active local CCHIS administrative/data-operations operator to record as the proof actor.",
        )
        parser.add_argument(
            "--output",
            default="",
            help="Optional path for a sanitized JSON evidence note.",
        )

    def handle(self, *args, **options):
        if not dhis2_api_configured():
            raise CommandError(
                "dhis2_configuration_invalid: proof requires SOURCE_DATA_DHIS2_BASE_URL, "
                "an auth method, SOURCE_DATA_DHIS2_MAPPING_JSON, and SOURCE_DATA_DHIS2_QUERY_JSON."
            )
        try:
            operator = resolve_dhis2_operator(options["operator_username"])
        except Dhis2OperatorError as error:
            raise CommandError(error.code) from error

        canonical_count_before = SurveillanceRecord.objects.count()
        first = run_source_data_connector_refresh(
            connector_key="dhis2_surveillance_weekly",
            actor=operator,
            options={"proof": True, "proof_attempt": 1},
            force=True,
        )
        canonical_count_after_first = SurveillanceRecord.objects.count()
        second = None
        if first.status == SourceDataConnectorRun.STATUS_SUCCESS:
            second = run_source_data_connector_refresh(
                connector_key="dhis2_surveillance_weekly",
                actor=operator,
                options={"proof": True, "proof_attempt": 2},
                force=True,
            )
        canonical_count_after_second = SurveillanceRecord.objects.count()
        evidence = self._evidence_for_pair(
            first,
            second,
            canonical_count_before=canonical_count_before,
            canonical_count_after_first=canonical_count_after_first,
            canonical_count_after_second=canonical_count_after_second,
        )
        output_path = str(options["output"] or "").strip()
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evidence, cls=DjangoJSONEncoder, indent=2, sort_keys=True), encoding="utf-8")
        self.stdout.write(json.dumps(evidence, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        if not evidence["passed"]:
            raise CommandError(str(evidence.get("failure_code") or "dhis2_play_proof_failed"))

    @staticmethod
    def _interop_for_run(connector_run: SourceDataConnectorRun | None) -> InteroperabilityRun | None:
        if connector_run is None:
            return None
        interop_id = (connector_run.safe_metadata or {}).get("interoperability_run_id")
        if not interop_id:
            return None
        try:
            return InteroperabilityRun.objects.select_related("mapping_version").get(public_id=interop_id)
        except InteroperabilityRun.DoesNotExist:
            return None

    @classmethod
    def _evidence_for_pair(
        cls,
        first: SourceDataConnectorRun,
        second: SourceDataConnectorRun | None,
        *,
        canonical_count_before: int,
        canonical_count_after_first: int,
        canonical_count_after_second: int,
    ) -> dict:
        first_metadata = first.safe_metadata or {}
        second_metadata = (second.safe_metadata or {}) if second else {}
        first_interop = cls._interop_for_run(first)
        second_interop = cls._interop_for_run(second)
        first_lineage = (first_interop.lineage_metadata or {}) if first_interop else {}
        second_lineage = (second_interop.lineage_metadata or {}) if second_interop else {}
        second_idempotency = second_lineage.get("idempotency") or {}
        first_http = first_metadata.get("http_evidence") or first_lineage.get("http_evidence") or {}
        second_http = second_metadata.get("http_evidence") or second_lineage.get("http_evidence") or {}
        first_counts = first_metadata.get("count_summary") or first_lineage.get("count_summary") or {}
        second_counts = second_metadata.get("count_summary") or second_lineage.get("count_summary") or {}
        first_query_hash = first_metadata.get("query_identity_hash") or first_lineage.get("query_identity_hash")
        second_query_hash = second_metadata.get("query_identity_hash") or second_lineage.get("query_identity_hash")
        first_response_hash = first_metadata.get("response_payload_hash") or first_lineage.get("response_payload_hash")
        second_response_hash = second_metadata.get("response_payload_hash") or second_lineage.get("response_payload_hash")
        exact_replay = bool(
            second
            and second_idempotency.get("replay_detected") is True
            and first_query_hash
            and first_query_hash == second_query_hash
            and first_response_hash
            and first_response_hash == second_response_hash
        )
        first_receipts = first_http.get("http_receipts") or []
        second_receipts = second_http.get("http_receipts") or []
        first_discovery_receipts = first_http.get("discovery_http_receipts") or []
        second_discovery_receipts = second_http.get("discovery_http_receipts") or []
        actual_gets = bool(first_receipts and second_receipts) and all(
            receipt.get("method") == "GET"
            and isinstance(receipt.get("status_code"), int)
            and 200 <= receipt["status_code"] < 300
            for receipt in [
                *first_receipts,
                *second_receipts,
                *first_discovery_receipts,
                *second_discovery_receipts,
            ]
        )
        adapter_completed = bool(
            first.status == SourceDataConnectorRun.STATUS_SUCCESS
            and second
            and second.status == SourceDataConnectorRun.STATUS_SUCCESS
            and first_interop
            and second_interop
            and first_interop.status == InteroperabilityRun.STATUS_COMPLETED
            and second_interop.status == InteroperabilityRun.STATUS_COMPLETED
        )
        correction_path = bool(second_lineage.get("correction", {}).get("detected") and not exact_replay)
        passed = adapter_completed and actual_gets and (exact_replay or correction_path)
        first_status = first_http.get("http_status")
        second_status = second_http.get("http_status")
        return {
            "evidence_schema_version": "dhis2-play-proof-evidence-v2",
            "passed": passed,
            "failure_code": (
                ""
                if passed
                else "dhis2_play_replay_not_verified"
                if adapter_completed and not exact_replay and not correction_path
                else "dhis2_play_proof_failed"
            ),
            "play_instance_hostname": first_metadata.get("instance_hostname") or first_lineage.get("instance_hostname"),
            "dhis2_server_version": first_metadata.get("dhis2_server_version") or first_lineage.get("dhis2_server_version"),
            "api_resource": first_metadata.get("api_resource") or first_lineage.get("api_resource"),
            "http_result": first_status,
            "second_http_result": second_status,
            "http_evidence": {
                "first": first_http,
                "second": second_http,
                "actual_get_only": actual_gets,
            },
            "first_connector_run_id": first.id,
            "second_connector_run_id": second.id if second else None,
            "first_interoperability_run_id": str(first_interop.public_id) if first_interop else "",
            "second_interoperability_run_id": str(second_interop.public_id) if second_interop else "",
            "query_identity_hash": first_query_hash,
            "first_response_payload_hash": first_response_hash,
            "second_response_payload_hash": second_response_hash,
            "previous_ingestion_reference": second_idempotency.get("existing_ingestion_run_id"),
            "exact_replay_detected": exact_replay,
            "correction_path_demonstrated": correction_path,
            "canonical_record_count_before": canonical_count_before,
            "canonical_record_count_after_first": canonical_count_after_first,
            "canonical_record_count_after_second": canonical_count_after_second,
            "duplicate_record_delta": canonical_count_after_second - canonical_count_after_first,
            "first_counts": first_counts,
            "second_counts": second_counts,
            "source_count": first_counts.get("source_data_value_count", first.fetched_record_count),
            "mapped_count": first_counts.get("mapped_source_data_value_count", first_metadata.get("mapped_record_count", 0)),
            "rejected_count": first_counts.get("rejected_source_data_value_count", first_metadata.get("rejected_record_count", 0)),
            "mapping_version": first_metadata.get("mapping_version")
            or (first_interop.mapping_version.version_label if first_interop and first_interop.mapping_version_id else ""),
            "truth_classification": list(first_metadata.get("truth_classification") or ["DEMO", "NON_OPERATIONAL"]),
            "production_eligible": False,
            "mapping_scope": "DEMO_ONLY",
            "credential_material_present_in_persisted_evidence": False,
        }

    @classmethod
    def _evidence_for_run(cls, connector_run: SourceDataConnectorRun) -> dict:
        """Compatibility helper for callers inspecting a single run."""

        count = 0
        if connector_run.upload_batch_id:
            batch = connector_run.upload_batch
            if batch and batch.surveillance_ingestion_run_id:
                count = batch.surveillance_ingestion_run.surveillance_records.count()
        return cls._evidence_for_pair(
            connector_run,
            None,
            canonical_count_before=count,
            canonical_count_after_first=count,
            canonical_count_after_second=count,
        )
