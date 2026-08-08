from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings

from accounts.models import User
from .models import (
    ExternalDataElementMapping,
    ExternalOrgUnitMapping,
    ExternalSystem,
    ExternalValueSetMapping,
    InteroperabilityMappingVersion,
    InteroperabilityRun,
    SourceDataConnectorRun,
    SourceDataUploadBatch,
    SurveillanceRecord,
    SurveillanceTruthLevel,
    Ward,
)
from .source_data.dhis2 import (
    DHIS2_API_ADAPTER_KEY,
    Dhis2AggregateRow,
    Dhis2Client,
    Dhis2AuthenticationError,
    Dhis2MappingError,
    Dhis2OperatorError,
    Dhis2QueryScopeError,
    Dhis2RequestError,
    dhis2_api_configured,
    dhis2_failure_summary,
    load_dhis2_mapping,
    parse_dhis2_period,
    resolve_dhis2_operator,
    run_dhis2_connector_refresh,
    transform_dhis2_rows,
)


def demo_mapping(query=None):
    return load_dhis2_mapping(
        {
            "mapping_version": "DHIS2_PLAY_DEMO_CROSSWALK_V1",
            "mapping_status": "DEMO_ONLY",
            "reviewer_status": "DEMO_ONLY",
            "operational_eligible": False,
            "system_key": "dhis2_play_demo_test",
            "organisation_units": {
                "OU-DEMO-1": {
                    "external_display_name": "Demo reporting unit",
                    "cchis_ward_code": "DHIS2-DEMO-WARD-1",
                    "status": "ACTIVE",
                }
            },
            "data_elements": {
                "DE-SUSPECTED": {
                    "external_display_name": "Demo suspected count",
                    "canonical_field": "suspected_cases",
                    "status": "ACTIVE",
                },
                "DE-CONFIRMED": {
                    "external_display_name": "Demo confirmed count",
                    "canonical_field": "confirmed_cases",
                    "status": "ACTIVE",
                },
            },
            "category_option_combinations": {
                "COC-DEFAULT": {
                    "internal_value": "default",
                    "external_label": "default",
                    "status": "ACTIVE",
                }
            },
        },
        query=query
        or {
            "resource": "analytics",
            "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
            "page_size": 10,
        },
    )


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class Dhis2ClientTests(TestCase):
    def test_pat_auth_header_is_used_without_secret_in_safe_metadata(self):
        session = MagicMock()
        session.get.return_value = FakeResponse({"id": "user-1"})
        client = Dhis2Client(
            "https://play.example.test/stable-2-43-1",
            api_token="token-that-must-not-be-persisted",
            session=session,
        )

        self.assertEqual(client.get_json("me"), {"id": "user-1"})
        call_kwargs = session.get.call_args.kwargs
        self.assertEqual(call_kwargs["headers"]["Authorization"], "ApiToken token-that-must-not-be-persisted")
        self.assertNotIn("token-that-must-not-be-persisted", str(client.safe_auth_metadata))
        self.assertEqual(client.safe_auth_metadata["credential_values_exposed"], False)

    def test_basic_auth_is_supported_over_https(self):
        session = MagicMock()
        session.get.return_value = FakeResponse({"id": "user-1"})
        client = Dhis2Client(
            "https://play.example.test/stable-2-43-1",
            username="admin",
            password="district",
            session=session,
        )

        client.get_json("me")

        auth = session.get.call_args.kwargs["auth"]
        self.assertEqual(auth.username, "admin")
        self.assertEqual(auth.password, "district")
        self.assertEqual(client.auth_scheme, "basic")

    def test_pagination_advances_page_without_logging_credentials(self):
        session = MagicMock()
        session.get.side_effect = [
            FakeResponse({"rows": [{"id": 1}], "pager": {"page": 1, "pageCount": 2, "pageSize": 1}}),
            FakeResponse({"rows": [{"id": 2}], "pager": {"page": 2, "pageCount": 2, "pageSize": 1}}),
        ]
        client = Dhis2Client("https://play.example.test", api_token="pat", session=session)

        payloads = client.get_paginated("organisationUnits", params={"pageSize": 1}, row_key="rows")

        self.assertEqual([payload["rows"][0]["id"] for payload in payloads], [1, 2])
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["page"], 2)

    def test_http_receipts_are_actual_get_statuses_and_redirects_are_not_followed(self):
        session = MagicMock()
        session.get.return_value = FakeResponse({"id": "user-1"}, status_code=200)
        client = Dhis2Client("https://play.example.test", api_token="pat", session=session)

        client.get_json("me")

        self.assertEqual(client.request_receipts[0]["method"], "GET")
        self.assertEqual(client.request_receipts[0]["resource"], "me")
        self.assertEqual(client.request_receipts[0]["status_code"], 200)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

        session.get.return_value = FakeResponse({}, status_code=302)
        with self.assertRaises(Dhis2RequestError) as context:
            client.get_json("system/info")
        self.assertEqual(context.exception.code, "dhis2_response_invalid")

    def test_timeout_authentication_rate_limit_and_server_errors_use_stable_codes(self):
        timeout_session = MagicMock()
        timeout_session.get.side_effect = requests.Timeout()
        with self.assertRaises(Dhis2RequestError) as timeout_context:
            Dhis2Client(
                "https://play.example.test",
                api_token="pat",
                max_retries=1,
                session=timeout_session,
            ).get_json("me")
        self.assertEqual(timeout_context.exception.code, "dhis2_timeout")
        self.assertEqual(timeout_session.get.call_count, 2)

        auth_session = MagicMock()
        auth_session.get.return_value = FakeResponse({}, status_code=401)
        with self.assertRaises(Dhis2AuthenticationError):
            Dhis2Client("https://play.example.test", api_token="pat", session=auth_session).get_json("me")

        rate_session = MagicMock()
        rate_session.get.return_value = FakeResponse({}, status_code=429)
        with self.assertRaises(Dhis2RequestError) as rate_context:
            Dhis2Client(
                "https://play.example.test",
                api_token="pat",
                max_retries=1,
                session=rate_session,
            ).get_json("me")
        self.assertEqual(rate_context.exception.code, "dhis2_rate_limited")
        self.assertEqual(rate_session.get.call_count, 2)

        server_session = MagicMock()
        server_session.get.return_value = FakeResponse({}, status_code=503)
        with self.assertRaises(Dhis2RequestError) as server_context:
            Dhis2Client(
                "https://play.example.test",
                api_token="pat",
                max_retries=1,
                session=server_session,
            ).get_json("me")
        self.assertEqual(server_context.exception.code, "dhis2_server_error")
        self.assertEqual(server_session.get.call_count, 2)

    def test_malformed_json_is_response_invalid_and_not_raw_exception_text(self):
        class MalformedResponse(FakeResponse):
            def json(self):
                raise ValueError("sentinel-secret")

        session = MagicMock()
        session.get.return_value = MalformedResponse({})
        with self.assertRaises(Dhis2RequestError) as context:
            Dhis2Client("https://play.example.test", api_token="pat", session=session).get_json("me")
        self.assertEqual(context.exception.code, "dhis2_response_invalid")
        self.assertNotIn("sentinel-secret", str(dhis2_failure_summary(context.exception)))


class Dhis2MappingTests(TestCase):
    def test_period_parser_handles_week_month_and_rejects_malformed_values(self):
        self.assertEqual(parse_dhis2_period("2026W18"), (date(2026, 4, 27), date(2026, 5, 3)))
        start, end = parse_dhis2_period("202604")
        self.assertEqual(start.isoformat(), "2026-04-01")
        self.assertEqual(end.isoformat(), "2026-04-30")
        with self.assertRaises(Dhis2MappingError):
            parse_dhis2_period("2026W99")
        with self.assertRaises(Dhis2MappingError):
            parse_dhis2_period("not-a-period")

    def test_operational_eligible_requires_the_boolean_false_and_scope_is_demo_only(self):
        for value in ("false", 0, 1, True, None):
            with self.subTest(value=value):
                payload = {
                    "mapping_version": "v1",
                    "mapping_status": "DEMO_ONLY",
                    "reviewer_status": "DEMO_ONLY",
                    "operational_eligible": value,
                    "organisation_units": {"OU-DEMO-1": {"cchis_ward_code": "W1"}},
                    "data_elements": {"DE-SUSPECTED": {"canonical_field": "suspected_cases"}},
                    "query": {
                        "resource": "analytics",
                        "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
                    },
                }
                with self.assertRaises(Dhis2MappingError):
                    load_dhis2_mapping(payload)

    def test_bounded_query_rejects_wildcards_multiple_periods_and_unmapped_uids(self):
        invalid_queries = [
            {
                "resource": "analytics",
                "params": {"dimension": ["dx:*", "ou:OU-DEMO-1", "pe:2026W18"]},
            },
            {
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18;2026W19"]},
            },
            {
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-UNKNOWN", "ou:OU-DEMO-1", "pe:2026W18"]},
            },
            {
                "resource": "analytics",
                "params": {
                    "dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"],
                    "startDate": "2026-04-01",
                },
            },
        ]
        for query in invalid_queries:
            with self.subTest(query=query):
                with self.assertRaises(Dhis2QueryScopeError):
                    demo_mapping(query=query)

    def test_data_value_sets_are_bounded_and_zero_values_are_preserved(self):
        mapping = demo_mapping(
            query={
                "resource": "dataValueSets",
                "params": {
                    "dataElement": "DE-SUSPECTED",
                    "orgUnit": "OU-DEMO-1",
                    "period": "2026W18",
                },
                "page_size": 10,
            }
        )
        session = MagicMock()
        session.get.return_value = FakeResponse(
            {
                "dataValues": [
                    {
                        "dataElement": "DE-SUSPECTED",
                        "orgUnit": "OU-DEMO-1",
                        "period": "2026W18",
                        "value": 0,
                        "categoryOptionCombo": "COC-DEFAULT",
                    }
                ]
            }
        )
        rows, metadata = Dhis2Client("https://play.example.test", api_token="pat", session=session).fetch_aggregate(
            mapping.query
        )
        self.assertEqual(rows[0].value, "0")
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_receipts"][0]["method"], "GET")

    def test_discovery_rejects_uid_mismatch(self):
        session = MagicMock()
        session.get.side_effect = [
            FakeResponse({"id": "user-1", "userCredentials": {"username": "demo"}}),
            FakeResponse({"version": "2.43.1"}),
            FakeResponse({"id": "OU-WRONG", "name": "Wrong unit"}),
        ]
        with self.assertRaises(Dhis2MappingError) as context:
            Dhis2Client("https://play.example.test", api_token="pat", session=session).discover(demo_mapping())
        self.assertEqual(context.exception.code, "dhis2_discovery_uid_mismatch")

    def test_transform_uses_explicit_uids_and_quarantines_unknown_or_invalid_rows(self):
        mapping = demo_mapping()
        transformation = transform_dhis2_rows(
            [
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "7", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-CONFIRMED", "OU-DEMO-1", "2026W18", "2", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-SUSPECTED", "OU-UNKNOWN", "2026W18", "3", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-UNKNOWN", "OU-DEMO-1", "2026W18", "3", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "bad", "3", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "1.5", "COC-DEFAULT"),
            ],
            mapping=mapping,
            instance_hostname="play.example.test",
            query_metadata={"resource": "analytics", "params": {"dimension": ["demo"]}},
            retrieved_at="2026-08-08T10:00:00+00:00",
            connector_run_id=11,
        )

        self.assertEqual(transformation.raw_record_count, 6)
        self.assertEqual(transformation.mapped_record_count, 1)
        self.assertEqual(transformation.mapped_source_data_value_count, 2)
        self.assertEqual(transformation.rejected_source_data_value_count, 4)
        self.assertEqual(transformation.canonical_grouped_row_count, 1)
        self.assertEqual(
            {item["code"] for item in transformation.rejected_rows},
            {"unknown_organisation_unit", "unknown_data_element", "invalid_period_or_value"},
        )
        row = transformation.rows[0]
        self.assertEqual(row["ward_code"], "DHIS2-DEMO-WARD-1")
        self.assertEqual(row["suspected_cases"], "7")
        self.assertEqual(row["confirmed_cases"], "2")
        self.assertEqual(row["truth_level"], SurveillanceTruthLevel.SEEDED_DEMO)
        self.assertEqual(row["dhis2_connector_run_id"], "11")
        self.assertEqual(row["dhis2_instance_hostname"], "play.example.test")
        self.assertEqual(row["source_ref"].count(":row:"), 1)
        self.assertNotEqual(row["source_ref"], transformation.source_ref)
        self.assertEqual(len(row["dhis2_row_identity_hash"]), 64)
        self.assertEqual(len(transformation.query_identity_hash), 64)
        self.assertEqual(len(transformation.response_payload_hash), 64)
        self.assertIn("DEMO", row["notes"])

        changed_transformation = transform_dhis2_rows(
            [
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "8", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-CONFIRMED", "OU-DEMO-1", "2026W18", "2", "COC-DEFAULT"),
            ],
            mapping=mapping,
            instance_hostname="play.example.test",
            query_metadata={"resource": "analytics", "params": {"dimension": ["demo"]}},
        )
        self.assertEqual(row["dhis2_row_identity_hash"], changed_transformation.rows[0]["dhis2_row_identity_hash"])
        self.assertNotEqual(row["source_ref"], changed_transformation.rows[0]["source_ref"])

    def test_unknown_category_option_combo_is_rejected(self):
        transformation = transform_dhis2_rows(
            [Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "1", "COC-UNKNOWN")],
            mapping=demo_mapping(),
            instance_hostname="play.example.test",
            query_metadata={
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
            },
        )
        self.assertEqual(transformation.rows, [])
        self.assertEqual(transformation.rejected_rows[0]["code"], "unknown_category_option_combo")

        mapping_without_categories = load_dhis2_mapping(
            {
                "mapping_version": "DHIS2_PLAY_DEMO_NO_CATEGORY_MAP",
                "mapping_status": "DEMO_ONLY",
                "reviewer_status": "DEMO_ONLY",
                "operational_eligible": False,
                "organisation_units": {"OU-DEMO-1": {"cchis_ward_code": "DHIS2-DEMO-WARD-1"}},
                "data_elements": {"DE-SUSPECTED": {"canonical_field": "suspected_cases"}},
                "query": {
                    "resource": "analytics",
                    "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
                },
            }
        )
        unmapped = transform_dhis2_rows(
            [Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "1", "COC-UNKNOWN")],
            mapping=mapping_without_categories,
            instance_hostname="play.example.test",
            query_metadata={
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
            },
        )
        self.assertEqual(unmapped.rows, [])
        self.assertEqual(unmapped.rejected_rows[0]["code"], "unknown_category_option_combo")


class Dhis2EndToEndPathTests(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="DHIS2 Play Demo Ward 1",
            county="DHIS2 Play Demo",
            ward_code="DHIS2-DEMO-WARD-1",
        )
        self.mapping = demo_mapping()
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.client = MagicMock()
        self.client.instance_hostname = "play.example.test"
        self.client.auth_scheme = "basic"
        self.client.api_token = ""
        self.client.base_url = "https://play.example.test/stable-2-43-1"
        self.client.discover.return_value = {
            "me": {"id": "demo-user", "displayName": "Demo User", "username_present": True},
            "server_version": "2.43.1",
            "organisation_units": [{"id": "OU-DEMO-1", "name": "Demo reporting unit"}],
            "data_elements": [{"id": "DE-SUSPECTED", "name": "Demo suspected count"}],
            "retrieved_at": "2026-08-08T10:00:00+00:00",
        }
        self.client.fetch_aggregate.return_value = (
            [
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "7", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-CONFIRMED", "OU-DEMO-1", "2026W18", "2", "COC-DEFAULT"),
            ],
            {
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
                "page_count": 1,
            },
        )
        self.client.api_url.side_effect = lambda resource: f"https://play.example.test/api/{resource}"

    def connector_run(self):
        return SourceDataConnectorRun.objects.create(
            connector_key="dhis2_surveillance_weekly",
            target_feed_key="surveillance_weekly_aggregate",
            feed_mode="api",
            source_name="DHIS2 Play demo aggregate",
            safe_metadata={"credential_values_exposed": False},
        )

    def run_import(self, connector_run):
        with override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_DHIS2_BASE_URL="https://play.example.test/stable-2-43-1",
            SOURCE_DATA_DHIS2_USERNAME="admin",
            SOURCE_DATA_DHIS2_PASSWORD="district",
            SOURCE_DATA_DHIS2_MAPPING_JSON="{}",
            SOURCE_DATA_DHIS2_QUERY_JSON="{}",
            CCHIS_ENVIRONMENT="local",
        ), patch("risk.source_data.dhis2.dhis2_mapping_from_settings", return_value=self.mapping), patch(
            "risk.source_data.dhis2.dhis2_client_from_settings", return_value=self.client
        ):
            return run_dhis2_connector_refresh(connector_run=connector_run)

    def test_read_only_response_is_validated_imported_provenance_preserved_and_replay_is_idempotent(self):
        first = self.run_import(self.connector_run())

        self.assertEqual(first.status, SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertEqual(first.safe_metadata["transport"], DHIS2_API_ADAPTER_KEY)
        self.assertFalse(first.safe_metadata["credential_values_exposed"])
        upload = SourceDataUploadBatch.objects.get(pk=first.upload_batch_id)
        self.assertEqual(upload.validation_status, SourceDataUploadBatch.VALIDATION_PASSED)
        self.assertEqual(upload.import_status, SourceDataUploadBatch.IMPORT_IMPORTED)
        self.assertEqual(upload.surveillance_ingestion_run.status, "SUCCESS")
        self.assertEqual(SurveillanceRecord.objects.count(), 2)

        record = SurveillanceRecord.objects.order_by("id").first()
        self.assertEqual(record.truth_level, SurveillanceTruthLevel.SEEDED_DEMO)
        self.assertEqual(record.raw_payload["provider_contract"]["dhis2_instance_hostname"], "play.example.test")
        self.assertEqual(record.raw_payload["provider_contract"]["dhis2_mapping_version"], "DHIS2_PLAY_DEMO_CROSSWALK_V1")
        self.assertEqual(record.raw_payload["provider_contract"]["dhis2_connector_run_id"], str(first.id))
        self.assertFalse(upload.surveillance_ingestion_run.results["truth_gates"]["production_alerting_eligible"])

        interop = InteroperabilityRun.objects.get(public_id=first.safe_metadata["interoperability_run_id"])
        self.assertEqual(interop.status, InteroperabilityRun.STATUS_COMPLETED)
        self.assertEqual(interop.records_seen, 2)
        self.assertEqual(interop.records_accepted, 2)
        self.assertEqual(interop.records_rejected, 0)
        self.assertFalse(interop.connector_config["credential_values_exposed"])
        self.assertEqual(interop.lineage_metadata["truth_classification"], ["DEMO", "NON_OPERATIONAL"])
        self.assertTrue(ExternalOrgUnitMapping.objects.exists())
        self.assertTrue(ExternalDataElementMapping.objects.exists())
        self.assertEqual(InteroperabilityMappingVersion.objects.get().status, InteroperabilityMappingVersion.STATUS_DRAFT)
        self.assertTrue(
            ExternalDataElementMapping.objects.filter(status="NEEDS_REVIEW").exists()
        )
        self.assertTrue(
            ExternalValueSetMapping.objects.filter(status="NEEDS_REVIEW").exists()
        )

        before = SurveillanceRecord.objects.count()
        second = self.run_import(self.connector_run())
        self.assertEqual(second.status, SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertTrue(second.safe_metadata["idempotency_replay"])
        self.assertEqual(second.safe_metadata["duplicate_canonical_records_created"], 0)
        self.assertEqual(SurveillanceRecord.objects.count(), before)

    def test_changed_payload_uses_amendment_path_and_supersedes_prior_records(self):
        first = self.run_import(self.connector_run())
        self.client.fetch_aggregate.return_value = (
            [
                Dhis2AggregateRow("DE-SUSPECTED", "OU-DEMO-1", "2026W18", "8", "COC-DEFAULT"),
                Dhis2AggregateRow("DE-CONFIRMED", "OU-DEMO-1", "2026W18", "2", "COC-DEFAULT"),
            ],
            {
                "resource": "analytics",
                "params": {"dimension": ["dx:DE-SUSPECTED", "ou:OU-DEMO-1", "pe:2026W18"]},
                "page_count": 1,
            },
        )
        second = self.run_import(self.connector_run())

        self.assertEqual(first.status, SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertEqual(second.status, SourceDataConnectorRun.STATUS_SUCCESS)
        self.assertFalse(second.safe_metadata["idempotency_replay"])
        self.assertEqual(second.safe_metadata["count_summary"]["canonical_grouped_row_count"], 1)
        self.assertTrue(
            second.safe_metadata["response_payload_hash"]
            != first.safe_metadata["response_payload_hash"]
        )
        second_upload = second.upload_batch
        second_run = second_upload.surveillance_ingestion_run
        self.assertEqual(second_upload.correction_mode, "amendment")
        self.assertEqual(second_run.correction_mode, "amendment")
        self.assertEqual(SurveillanceRecord.objects.count(), 4)
        amended = SurveillanceRecord.objects.filter(ingestion_run=second_run)
        self.assertEqual(amended.count(), 2)
        self.assertTrue(all(record.revision_number == 2 for record in amended))
        self.assertTrue(all(record.supersedes_record_ref for record in amended))
        self.assertTrue(
            SurveillanceRecord.objects.filter(
                ingestion_run=first.upload_batch.surveillance_ingestion_run,
                raw_payload__superseded_by_run_id=second_run.id,
            ).exists()
        )

    def test_sentinel_credentials_are_absent_from_persisted_evidence(self):
        sentinel = "sentinel-dhis2-credential-value"
        self.client.api_token = sentinel
        first = self.run_import(self.connector_run())
        interop = InteroperabilityRun.objects.get(public_id=first.safe_metadata["interoperability_run_id"])
        system = ExternalSystem.objects.get(system_key=self.mapping.system_key)
        evidence = {
            "connector": first.safe_metadata,
            "interop_config": interop.connector_config,
            "interop_lineage": interop.lineage_metadata,
            "upload": first.upload_batch.metadata,
            "system": system.lineage_metadata,
            "records": list(SurveillanceRecord.objects.values_list("raw_payload", flat=True)),
        }
        self.assertNotIn(sentinel, str(evidence))
        self.assertFalse(first.safe_metadata["credential_material_present_in_persisted_evidence"])

    def test_failure_metadata_never_contains_unexpected_exception_text(self):
        sentinel = "sentinel-password-value"
        error = ValueError(sentinel)
        summary = dhis2_failure_summary(error)
        self.assertEqual(summary["code"], "dhis2_unexpected_error")
        self.assertNotIn(sentinel, str(summary))

    def test_api_configuration_requires_explicit_query_and_authentication(self):
        with override_settings(
            SOURCE_DATA_DHIS2_BASE_URL="https://play.example.test",
            SOURCE_DATA_DHIS2_USERNAME="admin",
            SOURCE_DATA_DHIS2_PASSWORD="district",
            SOURCE_DATA_DHIS2_MAPPING_JSON='{"mapping_version":"v1"}',
            SOURCE_DATA_DHIS2_QUERY_JSON="",
        ):
            self.assertFalse(dhis2_api_configured())
        with override_settings(
            SOURCE_DATA_DHIS2_BASE_URL="https://play.example.test",
            SOURCE_DATA_DHIS2_USERNAME="",
            SOURCE_DATA_DHIS2_PASSWORD="",
            SOURCE_DATA_DHIS2_API_TOKEN="pat",
            SOURCE_DATA_DHIS2_MAPPING_JSON='{"mapping_version":"v1"}',
            SOURCE_DATA_DHIS2_QUERY_JSON='{"resource":"analytics","params":{"dimension":"x"}}',
        ):
            self.assertTrue(dhis2_api_configured())


class Dhis2OperatorTests(TestCase):
    def test_operator_must_be_active_and_admin_or_supervisor(self):
        admin = User.objects.create_user(username="dhis-admin", role=User.ROLE_ADMIN, is_active=True)
        self.assertEqual(resolve_dhis2_operator("dhis-admin"), admin)

        inactive = User.objects.create_user(username="dhis-inactive", role=User.ROLE_ADMIN, is_active=False)
        with self.assertRaises(Dhis2OperatorError) as inactive_context:
            resolve_dhis2_operator(inactive.username)
        self.assertEqual(inactive_context.exception.code, "dhis2_operator_inactive")

        analyst = User.objects.create_user(username="dhis-analyst", role=User.ROLE_ANALYST, is_active=True)
        with self.assertRaises(Dhis2OperatorError) as role_context:
            resolve_dhis2_operator(analyst.username)
        self.assertEqual(role_context.exception.code, "dhis2_operator_unauthorized")

        with self.assertRaises(Dhis2OperatorError) as missing_context:
            resolve_dhis2_operator("missing-dhis-operator")
        self.assertEqual(missing_context.exception.code, "dhis2_operator_not_found")
