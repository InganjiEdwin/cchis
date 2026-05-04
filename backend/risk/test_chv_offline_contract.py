from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    CHV,
    CHVDeviceRegistration,
    CHVOfflineRejectedSubmissionAudit,
    PreparednessAction,
    PreparednessActionEvent,
    SyncQueue,
    TriageSession,
    Ward,
)


class CHVOfflineContractPhaseOneTests(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(name="North Kanyamkago", county="Migori")
        self.other_ward = Ward.objects.create(name="Central Kanyamkago", county="Migori")
        self.chv_user = User.objects.create_user(
            username="offline-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
            ward=self.ward,
            phone_number="+254700000001",
        )
        self.other_chv_user = User.objects.create_user(
            username="other-offline-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
            ward=self.ward,
            phone_number="+254700000002",
        )
        self.supervisor_user = User.objects.create_user(
            username="offline-supervisor",
            password="StrongPass123!",
            role=User.ROLE_SUPERVISOR,
            ward=self.ward,
        )
        self.chv = CHV.objects.create(
            name="Akinyi",
            phone_number="+254700000001",
            ward=self.ward,
        )
        self.other_chv = CHV.objects.create(
            name="Otieno",
            phone_number="+254700000002",
            ward=self.ward,
        )

    def authenticate_chv(self):
        self.client.force_authenticate(self.chv_user)

    def authenticate_supervisor(self):
        self.client.force_authenticate(self.supervisor_user)

    def test_offline_contract_lists_prioritized_workflows_and_required_sync_contracts(self):
        self.authenticate_chv()

        response = self.client.get(reverse("chv-offline-contract"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflow_keys = [item["key"] for item in response.data["workflow_audit"]]
        self.assertEqual(
            workflow_keys,
            [
                "assigned_follow_up_tasks",
                "ward_guidance",
                "symptom_triage",
                "household_prevention_visit",
                "suspected_case_signal",
                "alert_follow_up_ack",
                "sync_later",
            ],
        )
        priorities = [item["priority"] for item in response.data["workflow_audit"]]
        self.assertEqual(priorities, sorted(priorities))
        triage_workflow = next(item for item in response.data["workflow_audit"] if item["key"] == "symptom_triage")
        self.assertIn("child_name", triage_workflow["risky_pii_fields"])
        self.assertEqual(response.data["contract_version"], "chv-offline-v1")
        self.assertEqual(response.data["session_scope"]["ward_id"], self.ward.id)
        self.assertEqual(response.data["session_scope"]["chv_public_id"], str(self.chv.public_id))

        sync_contracts = response.data["sync_contracts"]
        for key in [
            "device_registration",
            "user_session_scope",
            "download_bundle_version",
            "task_bundle",
            "guidance_bundle",
            "decision_support_rule_bundle",
            "upload_envelope",
            "idempotency_key",
            "conflict_state",
            "server_receipt",
            "sync_health_record",
        ]:
            self.assertIn(key, sync_contracts)

    def test_task_bundle_is_limited_to_chv_assigned_scope(self):
        self.authenticate_chv()
        own_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )
        other_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.other_chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )

        response = self.client.get(reverse("chv-offline-contract"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tasks = response.data["download_bundle"]["task_bundle"]["tasks"]
        task_ids = {task["task_public_id"] for task in tasks}
        self.assertIn(str(own_action.public_id), task_ids)
        self.assertNotIn(str(other_action.public_id), task_ids)

    def test_device_registration_records_scope_and_bundle_version(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-device-registration"),
            {
                "device_id": "field-device-001",
                "contract_version": "chv-offline-v1",
                "app_version": "1.0.0",
                "platform": "WEB",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        registration = CHVDeviceRegistration.objects.get()
        self.assertEqual(registration.user, self.chv_user)
        self.assertEqual(registration.chv, self.chv)
        self.assertEqual(registration.ward, self.ward)
        self.assertEqual(response.data["session_scope"]["chv_public_id"], str(self.chv.public_id))
        self.assertTrue(response.data["download_bundle_version"].startswith("chv-bundle-"))

    def test_versioned_sync_envelope_retries_by_idempotency_key(self):
        self.authenticate_chv()
        registration_response = self.client.post(
            reverse("chv-device-registration"),
            {"device_id": "field-device-002", "contract_version": "chv-offline-v1", "platform": "WEB"},
            format="json",
        )
        registration_id = registration_response.data["public_id"]
        payload = {
            "contract_version": "chv-offline-v1",
            "device_registration_id": registration_id,
            "session_scope": {"ward_id": self.ward.id},
            "download_bundle_version": registration_response.data["download_bundle_version"],
            "uploads": [
                {
                    "client_submission_id": "submission-001",
                    "idempotency_key": "idem-001",
                    "upload_type": "symptom_triage",
                    "payload": {
                        "diarrhea": True,
                        "vomiting": True,
                        "dehydration": False,
                        "fever": False,
                        "text_input": "Loose stool and vomiting",
                    },
                }
            ],
        }

        first_response = self.client.post(reverse("chv-sync"), payload, format="json")
        payload["uploads"][0]["client_submission_id"] = "submission-002"
        second_response = self.client.post(reverse("chv-sync"), payload, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SyncQueue.objects.count(), 1)
        self.assertEqual(TriageSession.objects.count(), 1)
        self.assertFalse(first_response.data["results"][0]["replayed"])
        self.assertTrue(second_response.data["results"][0]["replayed"])
        self.assertEqual(second_response.data["results"][0]["conflict_state"], SyncQueue.CONFLICT_REPLAYED)
        self.assertEqual(first_response.data["results"][0]["server_receipt"]["status"], "ACCEPTED")
        sync_item = SyncQueue.objects.get()
        self.assertEqual(sync_item.contract_version, "chv-offline-v1")
        self.assertEqual(sync_item.idempotency_key, "idem-001")
        self.assertEqual(sync_item.upload_type, SyncQueue.UPLOAD_SYMPTOM_TRIAGE)
        self.assertEqual(sync_item.device_registration.device_id, "field-device-002")
        sync_item.device_registration.refresh_from_db()
        self.assertIsNotNone(sync_item.device_registration.last_sync_at)

    def test_phase_four_prevention_visit_completes_action_and_writes_sync_audit_event(self):
        self.authenticate_chv()
        action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-003",
                "uploads": [
                    {
                        "client_submission_id": "visit-001",
                        "idempotency_key": "visit-idem-001",
                        "upload_type": "prevention_visit",
                        "payload_version": "chv-upload-payload-v1",
                        "payload": {
                            "action_public_id": str(action.public_id),
                            "ward_id": self.ward.id,
                            "visit_completed": True,
                            "households_reached_count": 4,
                            "messages_delivered_count": 4,
                            "water_treatment_demo": True,
                            "soap_or_handwashing_discussed": True,
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SyncQueue.objects.count(), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, PreparednessAction.STATUS_COMPLETED)
        self.assertEqual(action.completion_evidence["households_reached_count"], 4)
        result = response.data["results"][0]
        self.assertEqual(result["domain_record"]["type"], "preparedness_action")
        self.assertEqual(result["domain_record"]["public_id"], str(action.public_id))
        sync_item = SyncQueue.objects.get()
        self.assertEqual(sync_item.status, SyncQueue.STATUS_PROCESSED)
        self.assertEqual(sync_item.server_receipt["payload_version"], "chv-upload-payload-v1")
        self.assertTrue(
            action.events.filter(
                event_type=PreparednessActionEvent.EVENT_COMMENT,
                metadata__source="chv_offline_sync",
                metadata__sync_queue_id=sync_item.id,
            ).exists()
        )

    def test_phase_four_task_ack_replay_updates_action_once(self):
        self.authenticate_chv()
        action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )
        payload = {
            "contract_version": "chv-offline-v1",
            "ward_id": self.ward.id,
            "source_device_id": "field-device-004",
            "uploads": [
                {
                    "client_submission_id": "ack-001",
                    "idempotency_key": "ack-idem-001",
                    "upload_type": "task_ack",
                    "payload": {
                        "action_public_id": str(action.public_id),
                        "acknowledgment_status": "ACKNOWLEDGED",
                        "coded_reason": "field_follow_up_started",
                    },
                }
            ],
        }

        first_response = self.client.post(reverse("chv-sync"), payload, format="json")
        payload["uploads"][0]["client_submission_id"] = "ack-002"
        second_response = self.client.post(reverse("chv-sync"), payload, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(first_response.data["results"][0]["replayed"])
        self.assertTrue(second_response.data["results"][0]["replayed"])
        self.assertEqual(SyncQueue.objects.count(), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, PreparednessAction.STATUS_ACKNOWLEDGED)
        self.assertEqual(
            action.events.filter(
                event_type=PreparednessActionEvent.EVENT_COMMENT,
                metadata__source="chv_offline_sync",
            ).count(),
            1,
        )

    def test_phase_four_sync_rejects_action_outside_chv_scope(self):
        self.authenticate_chv()
        other_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.other_chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-005",
                "uploads": [
                    {
                        "client_submission_id": "ack-out-of-scope-001",
                        "idempotency_key": "ack-out-of-scope-idem-001",
                        "upload_type": "task_ack",
                        "payload": {
                            "action_public_id": str(other_action.public_id),
                            "acknowledgment_status": "ACKNOWLEDGED",
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["conflict_state"], SyncQueue.CONFLICT_SCOPE_MISMATCH)
        self.assertIn("sync_queue_id", response.data)
        self.assertEqual(SyncQueue.objects.count(), 1)
        rejected_sync = SyncQueue.objects.get()
        self.assertEqual(rejected_sync.status, SyncQueue.STATUS_FAILED)
        self.assertEqual(rejected_sync.conflict_state, SyncQueue.CONFLICT_SCOPE_MISMATCH)
        self.assertEqual(rejected_sync.server_receipt["status"], "REJECTED")
        self.assertEqual(rejected_sync.server_receipt["conflict_state"], SyncQueue.CONFLICT_SCOPE_MISMATCH)
        other_action.refresh_from_db()
        self.assertEqual(other_action.status, PreparednessAction.STATUS_ASSIGNED)

    def test_phase_four_sync_rejects_payload_ward_scope_mismatch(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-006",
                "uploads": [
                    {
                        "client_submission_id": "ward-mismatch-001",
                        "idempotency_key": "ward-mismatch-idem-001",
                        "upload_type": "symptom_triage",
                        "payload": {
                            "ward_id": self.other_ward.id,
                            "diarrhea": True,
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["conflict_state"], SyncQueue.CONFLICT_SCOPE_MISMATCH)
        self.assertIn("sync_queue_id", response.data)
        self.assertEqual(SyncQueue.objects.count(), 1)
        rejected_sync = SyncQueue.objects.get()
        self.assertEqual(rejected_sync.status, SyncQueue.STATUS_FAILED)
        self.assertEqual(rejected_sync.conflict_state, SyncQueue.CONFLICT_SCOPE_MISMATCH)
        self.assertEqual(rejected_sync.server_receipt["status"], "REJECTED")

    def test_phase_four_rejected_sync_retry_reuses_rejection_record(self):
        self.authenticate_chv()
        other_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.other_chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )
        payload = {
            "contract_version": "chv-offline-v1",
            "ward_id": self.ward.id,
            "source_device_id": "field-device-retry-rejected",
            "uploads": [
                {
                    "client_submission_id": "ack-rejected-retry-001",
                    "idempotency_key": "ack-rejected-retry-idem-001",
                    "upload_type": "task_ack",
                    "payload": {
                        "action_public_id": str(other_action.public_id),
                        "acknowledgment_status": "ACKNOWLEDGED",
                    },
                }
            ],
        }

        first_response = self.client.post(reverse("chv-sync"), payload, format="json")
        second_response = self.client.post(reverse("chv-sync"), payload, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(second_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(SyncQueue.objects.count(), 1)
        self.assertEqual(first_response.data["sync_queue_id"], second_response.data["sync_queue_id"])
        self.assertEqual(SyncQueue.objects.get().server_receipt["status"], "REJECTED")

    def test_phase_four_sync_rejects_unsupported_payload_version(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-007",
                "uploads": [
                    {
                        "client_submission_id": "bad-version-001",
                        "idempotency_key": "bad-version-idem-001",
                        "upload_type": "symptom_triage",
                        "payload_version": "chv-upload-payload-v0",
                        "payload": {
                            "diarrhea": True,
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payload_version", str(response.data))

    def test_serializer_level_unsafe_payload_records_sanitized_rejection_audit(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-prevalidation",
                "uploads": [
                    {
                        "client_submission_id": "unsafe-001",
                        "idempotency_key": "unsafe-idem-001",
                        "upload_type": "symptom_triage",
                        "payload": {
                            "diarrhea": True,
                            "household_name": "Jane Doe",
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SyncQueue.objects.count(), 0)
        audit = CHVOfflineRejectedSubmissionAudit.objects.get()
        self.assertEqual(audit.ward, self.ward)
        self.assertEqual(audit.source_device_id, "field-device-prevalidation")
        self.assertEqual(audit.client_submission_id, "unsafe-001")
        self.assertEqual(audit.idempotency_key, "unsafe-idem-001")
        self.assertEqual(audit.upload_type, SyncQueue.UPLOAD_SYMPTOM_TRIAGE)
        self.assertEqual(audit.rejection_stage, CHVOfflineRejectedSubmissionAudit.STAGE_PII_MINIMIZATION)
        self.assertEqual(audit.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(audit.request_body_hmac), 64)
        self.assertIn("uploads.0.payload.household_name", audit.field_paths)
        self.assertNotIn("Jane Doe", audit.safe_error_summary)
        self.assertNotIn("Jane Doe", str(audit.field_paths))

        self.authenticate_supervisor()
        monitoring_response = self.client.get(reverse("chv-offline-monitoring"))

        self.assertEqual(monitoring_response.status_code, status.HTTP_200_OK)
        self.assertEqual(monitoring_response.data["metrics"]["pre_validation_rejections_24h"], 1)
        checks = {check["key"]: check for check in monitoring_response.data["audit_checks"]}
        self.assertEqual(checks["pre_validation_rejections"]["count"], 1)
        rejected_audit = monitoring_response.data["recent_rejected_submission_audits"][0]
        self.assertEqual(rejected_audit["public_id"], str(audit.public_id))
        self.assertEqual(rejected_audit["rejection_stage"], CHVOfflineRejectedSubmissionAudit.STAGE_PII_MINIMIZATION)
        self.assertNotIn("Jane Doe", str(rejected_audit))

    def test_missing_sync_device_identity_records_sanitized_rejection_audit(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "uploads": [
                    {
                        "client_submission_id": "missing-device-001",
                        "idempotency_key": "missing-device-idem-001",
                        "upload_type": "symptom_triage",
                        "payload": {
                            "diarrhea": True,
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SyncQueue.objects.count(), 0)
        audit = CHVOfflineRejectedSubmissionAudit.objects.get()
        self.assertEqual(audit.ward, self.ward)
        self.assertEqual(audit.source_device_id, "")
        self.assertEqual(audit.client_submission_id, "missing-device-001")
        self.assertEqual(audit.idempotency_key, "missing-device-idem-001")
        self.assertEqual(audit.upload_type, SyncQueue.UPLOAD_SYMPTOM_TRIAGE)
        self.assertEqual(audit.rejection_stage, CHVOfflineRejectedSubmissionAudit.STAGE_ENVELOPE_VALIDATION)
        self.assertEqual(audit.error_code, "chv_offline_envelope_validation_failed")
        self.assertIn("source_device_id", audit.field_paths)
        self.assertNotIn("diarrhea", audit.safe_error_summary)
        self.assertNotIn("True", audit.safe_error_summary)

    def test_unsupported_contract_records_sanitized_rejection_audit_before_sync_queue(self):
        self.authenticate_chv()

        response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v0",
                "ward_id": self.ward.id,
                "source_device_id": "field-device-bad-contract",
                "uploads": [
                    {
                        "client_submission_id": "bad-contract-001",
                        "idempotency_key": "bad-contract-idem-001",
                        "upload_type": "symptom_triage",
                        "payload": {
                            "diarrhea": True,
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SyncQueue.objects.count(), 0)
        audit = CHVOfflineRejectedSubmissionAudit.objects.get()
        self.assertEqual(audit.rejection_stage, CHVOfflineRejectedSubmissionAudit.STAGE_CONTRACT_VERSION)
        self.assertEqual(audit.error_code, "chv_offline_contract_version_rejected")
        self.assertEqual(audit.contract_version, "chv-offline-v0")
        self.assertEqual(audit.source_device_id, "field-device-bad-contract")
        self.assertEqual(audit.status_code, status.HTTP_400_BAD_REQUEST)

    def test_phase_five_monitoring_reports_sync_metrics_and_audit_findings(self):
        self.authenticate_supervisor()
        now = timezone.now()
        registration = CHVDeviceRegistration.objects.create(
            user=self.chv_user,
            chv=self.chv,
            ward=self.ward,
            device_id="phase-five-device",
            contract_version="chv-offline-v1",
            platform=CHVDeviceRegistration.PLATFORM_WEB,
            last_bundle_version="bundle-current",
            last_seen_at=now - timedelta(hours=30),
            last_sync_at=now - timedelta(hours=30),
        )
        completed_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=now,
            completed_at=now,
        )
        stale_sync = SyncQueue.objects.create(
            source_device_id=registration.device_id,
            device_registration=registration,
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_PREVENTION_VISIT,
            client_submission_id="phase-five-processed",
            idempotency_key="phase-five-processed-idem",
            download_bundle_version="bundle-old",
            ward=self.ward,
            payload={"visit_completed": True},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=now - timedelta(minutes=20),
            server_receipt={
                "status": "ACCEPTED",
                "domain_record": {
                    "type": "preparedness_action",
                    "public_id": str(completed_action.public_id),
                    "status": PreparednessAction.STATUS_COMPLETED,
                },
            },
        )
        SyncQueue.objects.create(
            source_device_id=registration.device_id,
            device_registration=registration,
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_TASK_ACK,
            client_submission_id="phase-five-unlinked",
            idempotency_key="phase-five-unlinked-idem",
            download_bundle_version="bundle-current",
            ward=self.ward,
            payload={"acknowledgment_status": "ACKNOWLEDGED"},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=now - timedelta(minutes=15),
            server_receipt={
                "status": "ACCEPTED",
                "domain_record": {"type": "triage_session", "id": 999},
            },
        )
        SyncQueue.objects.create(
            source_device_id=registration.device_id,
            device_registration=registration,
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
            client_submission_id="phase-five-pending",
            idempotency_key="phase-five-pending-idem",
            ward=self.ward,
            payload={"diarrhea": True},
            status=SyncQueue.STATUS_PENDING,
        )
        for index in range(3):
            SyncQueue.objects.create(
                source_device_id="phase-five-rejecting-device",
                contract_version="chv-offline-v1",
                upload_type=SyncQueue.UPLOAD_TASK_ACK,
                client_submission_id=f"phase-five-rejected-{index}",
                idempotency_key=f"phase-five-rejected-idem-{index}",
                ward=self.ward,
                payload={},
                status=SyncQueue.STATUS_FAILED,
                processed_at=now - timedelta(minutes=10 - index),
                error_message="Preparedness action not found.",
            )
        SyncQueue.objects.create(
            source_device_id="phase-five-conflict-device",
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_TASK_ACK,
            client_submission_id="phase-five-conflict",
            idempotency_key="phase-five-conflict-idem",
            ward=self.ward,
            payload={},
            status=SyncQueue.STATUS_FAILED,
            conflict_state=SyncQueue.CONFLICT_UNSUPPORTED_UPLOAD,
            processed_at=now - timedelta(minutes=5),
            error_message="Unsupported CHV offline upload type.",
        )
        mismatched_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.other_chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ACKNOWLEDGED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=now,
        )
        PreparednessActionEvent.objects.create(
            preparedness_action=mismatched_action,
            actor=self.chv_user,
            event_type=PreparednessActionEvent.EVENT_COMMENT,
            old_status=PreparednessAction.STATUS_ASSIGNED,
            new_status=PreparednessAction.STATUS_ACKNOWLEDGED,
            metadata={"source": "chv_offline_sync", "sync_queue_id": stale_sync.id},
        )
        PreparednessActionEvent.objects.create(
            preparedness_action=completed_action,
            actor=self.chv_user,
            event_type=PreparednessActionEvent.EVENT_COMMENT,
            old_status=PreparednessAction.STATUS_IN_PROGRESS,
            new_status=PreparednessAction.STATUS_COMPLETED,
            metadata={"source": "chv_offline_sync", "sync_queue_id": stale_sync.id},
        )

        response = self.client.get(reverse("chv-offline-monitoring"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        metrics = response.data["metrics"]
        self.assertEqual(metrics["registered_chv_devices"], 1)
        self.assertEqual(metrics["active_chv_devices"], 1)
        self.assertEqual(metrics["successful_syncs_24h"], 2)
        self.assertEqual(metrics["failed_syncs_24h"], 4)
        self.assertEqual(metrics["pre_validation_rejections_24h"], 0)
        self.assertEqual(metrics["pending_uploads"], 1)
        self.assertEqual(metrics["stale_guidance_bundles"], 1)
        self.assertEqual(metrics["conflict_count_7d"], 1)
        self.assertIsNotNone(metrics["offline_task_completion_latency_minutes"])

        checks = {check["key"]: check for check in response.data["audit_checks"]}
        self.assertEqual(checks["out_of_assignment_data"]["count"], 1)
        self.assertEqual(checks["out_of_assignment_data"]["status"], "FAIL")
        self.assertEqual(checks["stale_bundle_action_completion"]["count"], 1)
        self.assertEqual(checks["repeated_rejected_uploads"]["count"], 3)
        self.assertEqual(checks["unlinked_field_submissions"]["count"], 1)
        self.assertEqual(checks["pre_validation_rejections"]["count"], 0)
        self.assertTrue(response.data["recent_sync_decisions"])
        self.assertTrue(any(item["decision"] == "REJECTED" for item in response.data["recent_sync_decisions"]))

    def test_phase_five_monitoring_explains_sync_api_rejection(self):
        self.authenticate_chv()
        other_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.other_chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now(),
        )
        rejection_response = self.client.post(
            reverse("chv-sync"),
            {
                "contract_version": "chv-offline-v1",
                "ward_id": self.ward.id,
                "source_device_id": "phase-five-api-rejected-device",
                "uploads": [
                    {
                        "client_submission_id": "phase-five-api-rejected",
                        "idempotency_key": "phase-five-api-rejected-idem",
                        "upload_type": "task_ack",
                        "payload": {
                            "action_public_id": str(other_action.public_id),
                            "acknowledgment_status": "ACKNOWLEDGED",
                        },
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(rejection_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("sync_queue_id", rejection_response.data)

        self.authenticate_supervisor()
        monitoring_response = self.client.get(reverse("chv-offline-monitoring"))

        self.assertEqual(monitoring_response.status_code, status.HTTP_200_OK)
        self.assertEqual(monitoring_response.data["metrics"]["failed_syncs_24h"], 1)
        self.assertEqual(monitoring_response.data["metrics"]["conflict_count_7d"], 1)
        decision = monitoring_response.data["recent_sync_decisions"][0]
        self.assertEqual(decision["id"], rejection_response.data["sync_queue_id"])
        self.assertEqual(decision["decision"], "REJECTED")
        self.assertEqual(decision["conflict_state"], SyncQueue.CONFLICT_SCOPE_MISMATCH)
        self.assertIn("Preparedness action not found", decision["explanation"])

    def test_phase_five_monitoring_respects_supervisor_ward_scope(self):
        self.authenticate_supervisor()
        now = timezone.now()
        own_registration = CHVDeviceRegistration.objects.create(
            user=self.chv_user,
            chv=self.chv,
            ward=self.ward,
            device_id="own-scope-device",
            contract_version="chv-offline-v1",
            platform=CHVDeviceRegistration.PLATFORM_WEB,
            last_bundle_version="bundle-own",
            last_seen_at=now,
        )
        other_user = User.objects.create_user(
            username="other-ward-offline-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
            ward=self.other_ward,
            phone_number="+254700000099",
        )
        other_chv = CHV.objects.create(
            name="Other Ward CHV",
            phone_number="+254700000099",
            ward=self.other_ward,
        )
        other_registration = CHVDeviceRegistration.objects.create(
            user=other_user,
            chv=other_chv,
            ward=self.other_ward,
            device_id="other-scope-device",
            contract_version="chv-offline-v1",
            platform=CHVDeviceRegistration.PLATFORM_WEB,
            last_bundle_version="bundle-other",
            last_seen_at=now,
        )
        SyncQueue.objects.create(
            source_device_id=own_registration.device_id,
            device_registration=own_registration,
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
            client_submission_id="own-scope-sync",
            idempotency_key="own-scope-idem",
            ward=self.ward,
            payload={"diarrhea": True},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=now,
            server_receipt={"status": "ACCEPTED", "domain_record": {"type": "triage_session", "id": 1}},
        )
        SyncQueue.objects.create(
            source_device_id=other_registration.device_id,
            device_registration=other_registration,
            contract_version="chv-offline-v1",
            upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
            client_submission_id="other-scope-sync",
            idempotency_key="other-scope-idem",
            ward=self.other_ward,
            payload={"diarrhea": True},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=now,
            server_receipt={"status": "ACCEPTED", "domain_record": {"type": "triage_session", "id": 2}},
        )

        response = self.client.get(reverse("chv-offline-monitoring"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["scope"]["ward_ids"], [self.ward.id])
        self.assertEqual(response.data["metrics"]["registered_chv_devices"], 1)
        self.assertEqual(response.data["metrics"]["successful_syncs_24h"], 1)
        self.assertEqual({row["ward_id"] for row in response.data["sync_health_by_ward"]}, {self.ward.id})

    def test_phase_five_monitoring_rejects_chv_role(self):
        self.authenticate_chv()

        response = self.client.get(reverse("chv-offline-monitoring"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
