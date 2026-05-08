from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User

from .interoperability import (
    CONNECTOR_REQUIRED_INTERFACE_METHODS,
    build_connector_request_for_run,
    classify_connector_failure,
    create_connector_failure_run,
    EXCHANGE_INVENTORY,
    active_data_element_mapping_for_field,
    active_mapping_version,
    active_org_unit_mapping_for_facility,
    active_org_unit_mapping_for_ward,
    active_value_set_mapping_for_internal_value,
    validate_connector_boundary_contract,
    validate_csv_template_contract,
    validate_exchange_inventory_contract,
    validate_interoperability_run_record_contract,
)
from .models import (
    ExternalDataElementMapping,
    ExternalOrgUnitMapping,
    ExternalSystem,
    ExternalValueSetMapping,
    HealthFacility,
    InteroperabilityMappingStatus,
    InteroperabilityMappingVersion,
    InteroperabilityRun,
    InteroperabilityRunError,
    InteroperabilityRunItem,
    RiskScore,
    Ward,
)
from .test_step_up_utils import force_authenticate_with_step_up


class InteroperabilityContractsTests(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="North Kanyamkago",
            county="Migori",
            sub_county="Nyatike",
            ward_code="MIG-NK",
        )
        self.facility = HealthFacility.objects.create(
            name="North Kanyamkago Dispensary",
            facility_code="FAC-NK-001",
            ward=self.ward,
        )
        self.admin_user = User.objects.create_user(
            username="interop-admin",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.supervisor_user = User.objects.create_user(
            username="interop-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
            ward=self.ward,
        )
        self.analyst_user = User.objects.create_user(
            username="interop-analyst",
            password="StrongPass123!",
            role=User.ROLE_ANALYST,
        )

    def create_external_system(self) -> ExternalSystem:
        return ExternalSystem.objects.create(
            system_key="dhis2",
            display_name="DHIS2",
            system_type=ExternalSystem.SYSTEM_DHIS2,
            owner="health_information_officer",
        )

    def create_active_mapping_version(self, system: ExternalSystem) -> InteroperabilityMappingVersion:
        return InteroperabilityMappingVersion.objects.create(
            system=system,
            version_label="migori-dhis2-v1",
            status=InteroperabilityMappingVersion.STATUS_ACTIVE,
            reviewed_by=self.admin_user,
        )

    def authenticate_admin(self):
        force_authenticate_with_step_up(self.client, self.admin_user, StepUpGrant.PURPOSE_SOURCE_DATA)

    def mapping_csv(self, *rows: str) -> str:
        header = (
            "external_identifier,external_display_name,internal_object_type,"
            "internal_object_public_id,internal_object_code,mapping_confidence,status"
        )
        return "\n".join([header, *rows])

    def test_exchange_inventory_has_required_csv_first_contract_for_every_exchange_type(self):
        self.assertEqual(validate_exchange_inventory_contract(), [])
        self.assertEqual(validate_csv_template_contract(), [])
        self.assertEqual(
            {item["exchange_type"] for item in EXCHANGE_INVENTORY},
            {exchange_type for exchange_type, _label in InteroperabilityRun.EXCHANGE_CHOICES},
        )
        for item in EXCHANGE_INVENTORY:
            self.assertTrue(item["source_owner"])
            self.assertIn("CSV", item["format"])
            self.assertTrue(item["cadence"])
            self.assertTrue(item["quality_risk"])
            self.assertTrue(item["csv_first"])

    def test_csv_template_file_is_downloadable_for_each_exchange_type(self):
        self.authenticate_admin()
        for exchange_type, _label in InteroperabilityRun.EXCHANGE_CHOICES:
            response = self.client.get(
                reverse("interoperability-csv-template-file", kwargs={"exchange_type": exchange_type})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["exchange_type"], exchange_type)
            self.assertEqual(response.data["content_type"], "text/csv")
            self.assertIn("payload_sha256", response.data)
            self.assertGreater(response.data["row_count"], 0)
            self.assertIn("\n", response.data["payload"])

    def test_connector_boundary_contract_builds_api_ready_request_from_run_records(self):
        self.assertEqual(validate_connector_boundary_contract(), [])
        system = self.create_external_system()
        system.auth_config_reference = "secrets://dhis2/migori-prod"
        system.api_base_url = "https://dhis2.example.test/api"
        system.save(update_fields=["auth_config_reference", "api_base_url", "updated_at"])
        run = InteroperabilityRun.objects.create(
            direction=InteroperabilityRun.DIRECTION_EXPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            system=system,
            status=InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION,
            dry_run=True,
            endpoint_url="https://dhis2.example.test/api/dataValueSets",
            operator=self.admin_user,
            export_payload={"records": [{"source_record_ref": "risk_score:1", "value": 0.82}]},
            connector_config={"connector_interface": list(CONNECTOR_REQUIRED_INTERFACE_METHODS)},
            completed_at=timezone.now(),
        )

        request = build_connector_request_for_run(run, cursor="next-page-token")

        self.assertEqual(request.run_public_id, str(run.public_id))
        self.assertEqual(request.direction, InteroperabilityRun.DIRECTION_EXPORT)
        self.assertEqual(request.exchange_type, InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT)
        self.assertEqual(request.system_key, "dhis2")
        self.assertEqual(request.endpoint_url, "https://dhis2.example.test/api/dataValueSets")
        self.assertEqual(request.auth_config_reference, "secrets://dhis2/migori-prod")
        self.assertEqual(request.source_reference, "https://dhis2.example.test/api/dataValueSets")
        self.assertTrue(request.dry_run)
        self.assertEqual(request.cursor, "next-page-token")
        self.assertEqual(request.payload["records"][0]["source_record_ref"], "risk_score:1")
        self.assertIn("paging_strategy", request.as_payload())

    def test_connector_failure_is_durable_and_does_not_mutate_canonical_data(self):
        system = self.create_external_system()
        system.auth_config_reference = "secrets://dhis2/migori-prod"
        system.api_base_url = "https://dhis2.example.test/api"
        system.save(update_fields=["auth_config_reference", "api_base_url", "updated_at"])
        mappings_before = ExternalOrgUnitMapping.objects.count()
        risk_scores_before = RiskScore.objects.count()
        failure = classify_connector_failure(
            "429 Too Many Requests",
            status_code=429,
            retry_after_seconds=120,
        )

        run = create_connector_failure_run(
            system_key="dhis2",
            direction=InteroperabilityRun.DIRECTION_EXPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            operator=self.admin_user,
            failure=failure,
            endpoint_url="https://dhis2.example.test/api/dataValueSets",
        )

        self.assertEqual(run.status, InteroperabilityRun.STATUS_FAILED)
        self.assertTrue(run.dry_run)
        self.assertEqual(run.records_rejected, 1)
        self.assertEqual(run.errors.get().error_code, "rate_limited")
        self.assertEqual(run.lineage_metadata["connector_failure_code"], "rate_limited")
        self.assertTrue(run.lineage_metadata["connector_failure_retryable"])
        self.assertEqual(run.lineage_metadata["connector_retry_after_seconds"], 120)
        self.assertFalse(run.lineage_metadata["canonical_mutation_performed"])
        self.assertEqual(run.dry_run_preview["next_action"], "retry_after_backoff")
        self.assertEqual(validate_interoperability_run_record_contract(run), [])
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), mappings_before)
        self.assertEqual(RiskScore.objects.count(), risk_scores_before)

    def test_org_unit_mapping_dry_run_records_unmapped_rows_without_mutation(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
            "OU-404,Unknown ward,WARD,,MISSING-CODE,0.40,ACTIVE",
        )

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_PARTIAL)
        self.assertTrue(response.data["dry_run"])
        self.assertEqual(response.data["records_seen"], 2)
        self.assertEqual(response.data["records_accepted"], 1)
        self.assertEqual(response.data["records_rejected"], 1)
        self.assertEqual(response.data["mapping_coverage"], 50.0)
        self.assertEqual(response.data["dry_run_preview"]["mapping_coverage_report"]["coverage_percent"], 50.0)
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)
        self.assertEqual(InteroperabilityRunError.objects.get().error_code, "mapping_unresolved_internal_ward")
        rejected_item = response.data["items"][1]
        self.assertEqual(rejected_item["status"], "UNMAPPED")
        self.assertEqual(rejected_item["safe_context"]["external_identifier"], "OU-404")
        self.assertEqual(response.data["source_reference"], "org-units.csv")
        self.assertEqual(response.data["contract_errors"], [])

        error_file_response = self.client.get(
            reverse("interoperability-run-error-file", kwargs={"public_id": response.data["public_id"]})
        )
        self.assertEqual(error_file_response.status_code, status.HTTP_200_OK)
        self.assertIn("mapping_unresolved_internal_ward", error_file_response.data["payload"])

    def test_failed_mapping_import_keeps_durable_run_error_context(self):
        self.authenticate_admin()
        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "broken-org-units.csv",
                "csv_text": "external_identifier\nOU-001\n",
                "confirm": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertEqual(response.data["source_reference"], "broken-org-units.csv")
        self.assertIsNotNone(response.data["completed_at"])
        self.assertEqual(response.data["contract_errors"], [])
        self.assertIn("csv_missing_required_columns", str(response.data["errors"]))
        review_item = response.data["items"][0]
        self.assertEqual(review_item["safe_context"]["external_identifier"], "OU-001")
        self.assertEqual(review_item["source_record_ref"], "broken-org-units.csv:2")
        run = InteroperabilityRun.objects.get(public_id=response.data["public_id"])
        self.assertEqual(run.errors.count(), 2)

    def test_clean_mapping_dry_run_is_confirmable_without_mutation(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION)
        self.assertTrue(response.data["dry_run"])
        self.assertTrue(response.data["dry_run_preview"]["confirmable"])
        self.assertTrue(response.data["dry_run_preview"]["operator_confirmation_required"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(response.data["dry_run_preview"]["next_action"], "confirm_import")
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)

    def test_confirmed_import_without_prior_clean_dry_run_is_blocked(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertFalse(response.data["dry_run"])
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(response.data["dry_run_preview"]["confirmation_error"], "prior_dry_run_required")
        self.assertEqual(response.data["dry_run_preview"]["next_action"], "run_clean_dry_run_first")
        self.assertIn("prior_dry_run_required", str(response.data["errors"]))
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)

    def test_confirmed_import_must_match_reviewed_dry_run_source_digest(self):
        self.authenticate_admin()
        dry_run_csv = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )
        changed_csv = self.mapping_csv(
            f"OU-002,North Kanyamkago changed,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )
        dry_run_response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": dry_run_csv,
                "confirm": False,
            },
            format="json",
        )
        self.assertEqual(dry_run_response.data["status"], InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION)

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": changed_csv,
                "confirm": True,
                "retry_of_public_id": dry_run_response.data["public_id"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertEqual(response.data["dry_run_preview"]["confirmation_error"], "dry_run_source_mismatch")
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertIn("dry_run_source_mismatch", str(response.data["errors"]))
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)

    def test_confirmed_import_with_rejected_rows_does_not_partially_mutate(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
            "OU-404,Unknown ward,WARD,,MISSING-CODE,0.40,ACTIVE",
        )

        dry_run_response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )
        self.assertEqual(dry_run_response.data["status"], InteroperabilityRun.STATUS_PARTIAL)

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": True,
                "retry_of_public_id": dry_run_response.data["public_id"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertFalse(response.data["dry_run"])
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(response.data["dry_run_preview"]["confirmation_error"], "dry_run_not_confirmable")
        self.assertIn("No mapping records were written", response.data["error_summary"])
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)
        mapping_version = InteroperabilityMappingVersion.objects.get(version_label="migori-dhis2-v1")
        self.assertEqual(mapping_version.status, InteroperabilityMappingVersion.STATUS_DRAFT)

    def test_confirmed_import_rejects_duplicate_mapping_rows_before_mutation(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
            f"OU-001,Duplicate external,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
            f"OU-002,Duplicate internal target,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )

        dry_run_response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "duplicate-org-units.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )
        self.assertEqual(dry_run_response.data["status"], InteroperabilityRun.STATUS_PARTIAL)

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "duplicate-org-units.csv",
                "csv_text": csv_text,
                "confirm": True,
                "retry_of_public_id": dry_run_response.data["public_id"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertEqual(response.data["records_accepted"], 1)
        self.assertEqual(response.data["records_rejected"], 2)
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(response.data["dry_run_preview"]["confirmation_error"], "dry_run_not_confirmable")
        self.assertIn("No mapping records were written", response.data["error_summary"])
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)
        self.assertIn("duplicate_external_identifier", str(response.data["errors"]))
        self.assertIn("duplicate_internal_object_mapping", str(response.data["errors"]))
        mapping_version = InteroperabilityMappingVersion.objects.get(version_label="migori-dhis2-v1")
        self.assertEqual(mapping_version.status, InteroperabilityMappingVersion.STATUS_DRAFT)

    def test_mapping_dry_run_rejects_invalid_confidence_and_status_without_normalization(self):
        self.authenticate_admin()
        second_ward = Ward.objects.create(
            name="West Kanyamkago",
            county="Migori",
            sub_county="Nyatike",
            ward_code="MIG-WK",
        )
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},bad-confidence,ACTIVE",
            f"OU-002,West Kanyamkago,WARD,{second_ward.public_id},{second_ward.ward_code},0.75,AUTO_APPROVED",
        )

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "bad-mapping-values.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_PARTIAL)
        self.assertEqual(response.data["records_accepted"], 0)
        self.assertEqual(response.data["records_rejected"], 2)
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertFalse(response.data["dry_run_preview"]["mutation_performed"])
        self.assertIn("invalid_mapping_confidence", str(response.data["errors"]))
        self.assertIn("invalid_mapping_status", str(response.data["errors"]))
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)

    def test_confirmed_org_unit_import_creates_versioned_mapping_and_retired_mapping_is_not_used(self):
        self.authenticate_admin()
        csv_text = self.mapping_csv(
            f"OU-001,North Kanyamkago,WARD,{self.ward.public_id},{self.ward.ward_code},0.95,ACTIVE",
        )

        dry_run_response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": False,
            },
            format="json",
        )
        self.assertEqual(dry_run_response.data["status"], InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION)
        self.assertEqual(ExternalOrgUnitMapping.objects.count(), 0)

        response = self.client.post(
            reverse("interoperability-org-unit-mapping-import"),
            {
                "system_key": "dhis2",
                "mapping_version_label": "migori-dhis2-v1",
                "source_file_name": "org-units.csv",
                "csv_text": csv_text,
                "confirm": True,
                "retry_of_public_id": dry_run_response.data["public_id"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_COMPLETED)
        self.assertEqual(response.data["retry_of"], dry_run_response.data["public_id"])
        self.assertTrue(response.data["dry_run_preview"]["mutation_performed"])
        self.assertEqual(response.data["dry_run_preview"]["next_action"], "mapping_records_written")
        mapping = ExternalOrgUnitMapping.objects.get()
        self.assertEqual(mapping.mapping_version.status, InteroperabilityMappingVersion.STATUS_ACTIVE)
        self.assertEqual(mapping.external_identifier, "OU-001")
        self.assertEqual(mapping.internal_object_public_id, str(self.ward.public_id))
        self.assertEqual(active_org_unit_mapping_for_ward(mapping.system, self.ward), mapping)

        mapping.status = InteroperabilityMappingStatus.RETIRED
        mapping.retired_date = timezone.localdate()
        mapping.save(update_fields=["status", "retired_date", "updated_at"])

        self.assertIsNone(active_org_unit_mapping_for_ward(mapping.system, self.ward))

    def test_risk_score_export_preview_requires_active_org_unit_and_data_element_mappings(self):
        self.authenticate_admin()
        system = self.create_external_system()
        mapping_version = self.create_active_mapping_version(system)
        ExternalOrgUnitMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            external_identifier="OU-001",
            external_display_name="North Kanyamkago",
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            internal_object_public_id=str(self.ward.public_id),
            internal_object_code=self.ward.ward_code,
            ward=self.ward,
            mapping_confidence=0.95,
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.82,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=7,
            rainfall_mm=12.5,
            flood_indicator=0.2,
            model_version="cholera-v1",
        )

        missing_mapping_response = self.client.post(
            reverse("interoperability-risk-score-export-preview"),
            {"system_key": "dhis2"},
            format="json",
        )

        self.assertEqual(missing_mapping_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(missing_mapping_response.data["status"], InteroperabilityRun.STATUS_PARTIAL)
        self.assertIn("required_data_element_mapping_missing", str(missing_mapping_response.data["errors"]))

        for internal_field, external_identifier in {
            "risk_score.score": "DE-RISK-SCORE",
            "risk_score.risk_level": "DE-RISK-LEVEL",
            "risk_score.predicted_cases": "DE-PREDICTED-CASES",
        }.items():
            ExternalDataElementMapping.objects.create(
                system=system,
                mapping_version=mapping_version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                internal_field=internal_field,
                external_identifier=external_identifier,
                status=InteroperabilityMappingStatus.ACTIVE,
                reviewed_by=self.admin_user,
            )

        preview_response = self.client.post(
            reverse("interoperability-risk-score-export-preview"),
            {"system_key": "dhis2"},
            format="json",
        )

        self.assertEqual(preview_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(preview_response.data["status"], InteroperabilityRun.STATUS_READY_FOR_CONFIRMATION)
        self.assertEqual(preview_response.data["records_accepted"], 1)
        payload_record = preview_response.data["export_payload"]["records"][0]
        self.assertEqual(payload_record["orgUnit"], "OU-001")
        self.assertEqual(preview_response.data["source_reference"], "cchis://risk-scores/latest")
        self.assertEqual(preview_response.data["contract_errors"], [])
        self.assertTrue(preview_response.data["dry_run_preview"]["confirmable"])
        self.assertEqual(preview_response.data["dry_run_preview"]["mapping_coverage_report"]["coverage_percent"], 100.0)
        csv_rows = preview_response.data["export_payload"]["csv"]["rows"]
        self.assertEqual(len(csv_rows), 3)
        self.assertEqual({row["source_record_ref"] for row in csv_rows}, {f"risk_score:{risk_score.id}"})
        self.assertEqual(
            {item["dataElement"] for item in payload_record["dataValues"]},
            {"DE-RISK-SCORE", "DE-RISK-LEVEL", "DE-PREDICTED-CASES"},
        )

    def test_export_failure_without_mapping_version_is_a_durable_run(self):
        self.authenticate_admin()
        response = self.client.post(
            reverse("interoperability-risk-score-export-preview"),
            {"system_key": "dhis2"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["direction"], InteroperabilityRun.DIRECTION_EXPORT)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_FAILED)
        self.assertEqual(response.data["source_reference"], "cchis://risk-scores/latest")
        self.assertIsNotNone(response.data["completed_at"])
        self.assertEqual(response.data["contract_errors"], [])
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertEqual(response.data["dry_run_preview"]["records_rejected"], 1)
        self.assertIn("active_mapping_version_missing", str(response.data["errors"]))
        run = InteroperabilityRun.objects.get(public_id=response.data["public_id"])
        self.assertEqual(run.errors.count(), 1)

    def test_export_unmapped_record_keeps_review_context(self):
        self.authenticate_admin()
        system = self.create_external_system()
        mapping_version = self.create_active_mapping_version(system)
        for internal_field, external_identifier in {
            "risk_score.score": "DE-RISK-SCORE",
            "risk_score.risk_level": "DE-RISK-LEVEL",
            "risk_score.predicted_cases": "DE-PREDICTED-CASES",
        }.items():
            ExternalDataElementMapping.objects.create(
                system=system,
                mapping_version=mapping_version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                internal_field=internal_field,
                external_identifier=external_identifier,
                status=InteroperabilityMappingStatus.ACTIVE,
                reviewed_by=self.admin_user,
            )
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.76,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=4,
            rainfall_mm=9.0,
            flood_indicator=0.1,
            model_version="cholera-v1",
        )

        response = self.client.post(
            reverse("interoperability-risk-score-export-preview"),
            {"system_key": "dhis2"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], InteroperabilityRun.STATUS_PARTIAL)
        self.assertEqual(response.data["contract_errors"], [])
        self.assertEqual(response.data["records_rejected"], 1)
        self.assertFalse(response.data["dry_run_preview"]["confirmable"])
        self.assertEqual(response.data["dry_run_preview"]["mapping_coverage_report"]["coverage_percent"], 0.0)
        review_item = response.data["items"][0]
        self.assertEqual(review_item["status"], "UNMAPPED")
        self.assertEqual(review_item["source_record_ref"], f"risk_score:{risk_score.id}")
        self.assertEqual(review_item["safe_context"]["ward_public_id"], str(self.ward.public_id))
        self.assertEqual(review_item["safe_context"]["risk_score_id"], risk_score.id)
        self.assertIn("org_unit_mapping_missing", str(response.data["errors"]))

    def test_active_mapping_helpers_ignore_retired_versions_and_mapping_records(self):
        system = self.create_external_system()
        mapping_version = self.create_active_mapping_version(system)
        retired_version = InteroperabilityMappingVersion.objects.create(
            system=system,
            version_label="retired-dhis2-v0",
            status=InteroperabilityMappingVersion.STATUS_RETIRED,
            retired_at=timezone.now(),
            reviewed_by=self.admin_user,
        )
        self.assertEqual(active_mapping_version(system), mapping_version)
        self.assertIsNone(active_mapping_version(system, retired_version.version_label))

        facility_mapping = ExternalOrgUnitMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            external_identifier="FAC-OU-001",
            external_display_name="North Kanyamkago Dispensary",
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_FACILITY,
            internal_object_public_id=str(self.facility.public_id),
            internal_object_code=self.facility.facility_code,
            facility=self.facility,
            mapping_confidence=0.95,
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        self.assertEqual(active_org_unit_mapping_for_facility(system, self.facility), facility_mapping)
        facility_mapping.status = InteroperabilityMappingStatus.RETIRED
        facility_mapping.retired_date = timezone.localdate()
        facility_mapping.save(update_fields=["status", "retired_date", "updated_at"])
        self.assertIsNone(active_org_unit_mapping_for_facility(system, self.facility))

        data_element_mapping = ExternalDataElementMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            internal_field="risk_score.score",
            external_identifier="DE-RISK-SCORE",
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        ExternalDataElementMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            internal_field="risk_score.risk_level",
            external_identifier="DE-RETIRED-RISK-LEVEL",
            status=InteroperabilityMappingStatus.RETIRED,
            retired_date=timezone.localdate(),
            reviewed_by=self.admin_user,
        )
        ExternalDataElementMapping.objects.create(
            system=system,
            mapping_version=retired_version,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            internal_field="risk_score.predicted_cases",
            external_identifier="DE-RETIRED-VERSION-PREDICTED-CASES",
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        self.assertEqual(
            active_data_element_mapping_for_field(
                system=system,
                mapping_version=mapping_version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                internal_field="risk_score.score",
            ),
            data_element_mapping,
        )
        self.assertIsNone(
            active_data_element_mapping_for_field(
                system=system,
                mapping_version=mapping_version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                internal_field="risk_score.risk_level",
            )
        )
        self.assertIsNone(
            active_data_element_mapping_for_field(
                system=system,
                mapping_version=retired_version,
                exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
                internal_field="risk_score.predicted_cases",
            )
        )

        value_mapping = ExternalValueSetMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            value_set_key="risk_level",
            internal_value="HIGH",
            external_value="dhis2-high",
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        ExternalValueSetMapping.objects.create(
            system=system,
            mapping_version=mapping_version,
            value_set_key="risk_level",
            internal_value="LOW",
            external_value="dhis2-low-retired",
            status=InteroperabilityMappingStatus.RETIRED,
            retired_date=timezone.localdate(),
            reviewed_by=self.admin_user,
        )
        ExternalValueSetMapping.objects.create(
            system=system,
            mapping_version=retired_version,
            value_set_key="risk_level",
            internal_value="MEDIUM",
            external_value="dhis2-medium-retired-version",
            status=InteroperabilityMappingStatus.ACTIVE,
            reviewed_by=self.admin_user,
        )
        self.assertEqual(
            active_value_set_mapping_for_internal_value(
                system=system,
                mapping_version=mapping_version,
                value_set_key="risk_level",
                internal_value="HIGH",
            ),
            value_mapping,
        )
        self.assertIsNone(
            active_value_set_mapping_for_internal_value(
                system=system,
                mapping_version=mapping_version,
                value_set_key="risk_level",
                internal_value="LOW",
            )
        )
        self.assertIsNone(
            active_value_set_mapping_for_internal_value(
                system=system,
                mapping_version=retired_version,
                value_set_key="risk_level",
                internal_value="MEDIUM",
            )
        )

    def test_retry_run_is_linked_and_dashboard_exposes_operating_contract(self):
        self.authenticate_admin()
        system = self.create_external_system()
        failed_run = InteroperabilityRun.objects.create(
            direction=InteroperabilityRun.DIRECTION_IMPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT,
            system=system,
            status=InteroperabilityRun.STATUS_FAILED,
            source_file_name="org-units.csv",
            operator=self.admin_user,
            error_summary="CSV validation failed before operator confirmation.",
            completed_at=timezone.now(),
            lineage_metadata={"source_file_sha256": "abc123"},
        )

        retry_response = self.client.post(
            reverse("interoperability-run-retry", kwargs={"public_id": failed_run.public_id}),
            {},
            format="json",
        )

        self.assertEqual(retry_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry_response.data["retry_of"], str(failed_run.public_id))
        self.assertEqual(retry_response.data["retry_of_public_id"], str(failed_run.public_id))
        self.assertEqual(retry_response.data["source_reference"], "org-units.csv")
        self.assertEqual(retry_response.data["contract_errors"], [])
        retry_run = InteroperabilityRun.objects.get(public_id=retry_response.data["public_id"])
        self.assertEqual(retry_run.retry_of, failed_run)

        dashboard_response = self.client.get(reverse("interoperability-dashboard"))
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard_response.data["schema_version"], "interoperability-contracts-v1")
        self.assertTrue(dashboard_response.data["exchange_inventory"])
        self.assertEqual(dashboard_response.data["exchange_inventory_contract_errors"], [])
        self.assertEqual(dashboard_response.data["csv_template_contract_errors"], [])
        self.assertEqual(dashboard_response.data["connector_boundary_contract_errors"], [])
        self.assertIn("retry_policy", dashboard_response.data["connector_boundary"])
        self.assertGreaterEqual(dashboard_response.data["summary"]["run_count"], 2)

    def test_run_detail_endpoint_returns_full_review_ledger_not_dashboard_sample(self):
        self.authenticate_admin()
        system = self.create_external_system()
        run = InteroperabilityRun.objects.create(
            direction=InteroperabilityRun.DIRECTION_IMPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT,
            system=system,
            status=InteroperabilityRun.STATUS_PARTIAL,
            source_file_name="large-org-units.csv",
            records_seen=30,
            records_accepted=0,
            records_rejected=30,
            mapping_coverage=0.0,
            operator=self.admin_user,
            error_summary="30 row(s) need review before this exchange can be trusted.",
            completed_at=timezone.now(),
        )
        for index in range(30):
            item = InteroperabilityRunItem.objects.create(
                run=run,
                row_number=index + 2,
                external_identifier=f"OU-{index:03d}",
                internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
                internal_object_code=f"MISSING-{index:03d}",
                status=InteroperabilityRunItem.STATUS_UNMAPPED,
                action=InteroperabilityRunItem.ACTION_NOOP,
                safe_context={"external_identifier": f"OU-{index:03d}"},
                source_record_ref=f"large-org-units.csv:{index + 2}",
            )
            InteroperabilityRunError.objects.create(
                run=run,
                item=item,
                error_code="mapping_unresolved_internal_ward",
                field_path="internal_object_public_id",
                safe_message="No active CCHIS ward matched the supplied public id or ward code.",
            )

        dashboard_response = self.client.get(reverse("interoperability-dashboard"))
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        dashboard_run = next(
            item for item in dashboard_response.data["runs"] if item["public_id"] == str(run.public_id)
        )
        self.assertEqual(len(dashboard_run["items"]), 25)
        self.assertEqual(len(dashboard_run["errors"]), 25)

        detail_response = self.client.get(reverse("interoperability-run-detail", kwargs={"public_id": run.public_id}))
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_response.data["items"]), 30)
        self.assertEqual(len(detail_response.data["errors"]), 30)
        self.assertEqual(detail_response.data["errors"][29]["item_row_number"], 31)

    def test_analyst_interoperability_read_surface_is_summary_only(self):
        system = self.create_external_system()
        system.auth_config_reference = "secrets://dhis2/migori-prod"
        system.api_base_url = "https://dhis2.example.test/api"
        system.save(update_fields=["auth_config_reference", "api_base_url", "updated_at"])
        run = InteroperabilityRun.objects.create(
            direction=InteroperabilityRun.DIRECTION_EXPORT,
            exchange_type=InteroperabilityRun.EXCHANGE_AGGREGATE_REPORT_EXPORT,
            system=system,
            status=InteroperabilityRun.STATUS_PARTIAL,
            dry_run=True,
            source_file_name="risk-score-export.csv",
            endpoint_url="https://dhis2.example.test/api/dataValueSets",
            records_seen=1,
            records_accepted=0,
            records_rejected=1,
            mapping_coverage=0.0,
            operator=self.admin_user,
            error_summary="1 row needs review before this exchange can be trusted.",
            dry_run_preview={
                "schema_version": "interoperability-export-preview-v1",
                "records_seen": 1,
                "records_accepted": 0,
                "records_rejected": 1,
                "mapping_coverage": 0.0,
                "mapping_coverage_report": {
                    "records_seen": 1,
                    "records_with_resolved_mapping": 0,
                    "records_requiring_review": 1,
                    "coverage_percent": 0.0,
                },
                "source_trace": ["risk_score:42"],
            },
            export_payload={
                "records": [
                    {
                        "orgUnit": "DHIS2-OU-SECRET",
                        "dataValues": [{"dataElement": "DE-RISK-SCORE", "value": 0.82}],
                    }
                ]
            },
            connector_config={"auth_config_reference": "secrets://dhis2/migori-prod"},
            completed_at=timezone.now(),
        )
        item = InteroperabilityRunItem.objects.create(
            run=run,
            row_number=2,
            external_identifier="DHIS2-OU-SECRET",
            internal_object_type=ExternalOrgUnitMapping.INTERNAL_WARD,
            internal_object_code="MISSING-WARD",
            status=InteroperabilityRunItem.STATUS_UNMAPPED,
            action=InteroperabilityRunItem.ACTION_NOOP,
            safe_context={"external_identifier": "DHIS2-OU-SECRET", "risk_score_id": 42},
            source_record_ref="risk_score:42",
        )
        InteroperabilityRunError.objects.create(
            run=run,
            item=item,
            error_code="org_unit_mapping_missing",
            field_path="orgUnit",
            safe_message="No active external org unit matched this CCHIS ward.",
        )

        self.client.force_authenticate(self.analyst_user)
        dashboard_response = self.client.get(reverse("interoperability-dashboard"))
        detail_response = self.client.get(reverse("interoperability-run-detail", kwargs={"public_id": run.public_id}))
        error_file_response = self.client.get(reverse("interoperability-run-error-file", kwargs={"public_id": run.public_id}))

        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        system_payload = dashboard_response.data["systems"][0]
        self.assertEqual(system_payload["auth_config_reference"], "")
        self.assertEqual(system_payload["api_base_url"], "")
        run_payload = dashboard_response.data["runs"][0]
        self.assertEqual(run_payload["source_file_name"], "")
        self.assertEqual(run_payload["endpoint_url"], "")
        self.assertEqual(run_payload["source_reference"], "")
        self.assertEqual(run_payload["operator_username"], "")
        self.assertEqual(run_payload["export_payload"], {})
        self.assertEqual(run_payload["items"], [])
        self.assertEqual(run_payload["errors"], [])
        self.assertNotIn("source_trace", run_payload["dry_run_preview"])
        self.assertEqual(
            run_payload["dry_run_preview"]["mapping_coverage_report"]["records_requiring_review"],
            1,
        )
        self.assertNotIn("DHIS2-OU-SECRET", str(run_payload))
        self.assertNotIn("secrets://dhis2/migori-prod", str(dashboard_response.data))
        self.assertEqual(detail_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(error_file_response.status_code, status.HTTP_403_FORBIDDEN)
