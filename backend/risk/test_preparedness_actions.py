import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import (
    Alert,
    AlertWorkflowState,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    FacilityReadinessEscalation,
    FacilityReadinessReview,
    HealthFacility,
    ModelRun,
    PreparednessAction,
    PreparednessActionEvent,
    RiskScore,
    Ward,
)
from .preparedness_action_audit import build_preparedness_action_ledger_audit
from .services import get_or_create_preparedness_action, sync_alert_workflow_for_ward, transition_preparedness_action


class PreparednessActionLedgerTestCase(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.ward = Ward.objects.create(
            name="Ledger Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.91,
        )
        self.other_ward = Ward.objects.create(
            name="Other Ledger Ward",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.54,
        )
        self.admin_user = self._create_user("prep_admin", User.ROLE_ADMIN, self.ward)
        self.supervisor_user = self._create_user("prep_supervisor", User.ROLE_SUPERVISOR, self.ward)
        self.analyst_user = self._create_user("prep_analyst", User.ROLE_ANALYST, self.other_ward)
        self.chv_user = self._create_user("prep_chv", User.ROLE_CHV, self.ward)
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="ledger-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=5,
            feature_schema_version="baseline-v1",
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases"],
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
                "execution_context": "test",
            },
            completed_at=timezone.now(),
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=148.0,
            flood_indicator=0.78,
            predicted_cases=21,
            source=RiskScore.SOURCE_MODEL,
            model_version="ledger-v1",
            decision_policy={"policy_version": "policy-v1", "decision": "urgent_alert"},
        )
        self.alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="operations-dashboard",
            message="High cholera risk requires field verification.",
            status=Alert.STATUS_DELIVERED,
        )
        self.facility = HealthFacility.objects.create(
            name="Ledger Ward Dispensary",
            facility_code="LEDGER-FAC-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254720200001",
        )
        self.chv = CHV.objects.create(
            name="Ledger CHV",
            phone_number="+254700200001",
            ward=self.ward,
            is_active=True,
            language="en",
        )

    def _create_user(self, username: str, role: str, ward: Ward) -> User:
        return User.objects.create_user(
            username=username,
            password=self.password,
            email=f"{username}@example.com",
            role=role,
            ward=ward,
            is_active=True,
        )

    def test_source_trigger_reuses_existing_active_action_and_records_lineage(self):
        action, created = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )

        self.assertTrue(created)
        self.assertEqual(action.source_trigger_ref, f"alert:{self.alert.public_id}")
        self.assertEqual(action.risk_score, self.risk_score)
        self.assertEqual(action.model_run, self.model_run)
        self.assertEqual(action.decision_policy_version, "policy-v1")
        self.assertEqual(
            list(action.events.values_list("event_type", flat=True)),
            [PreparednessActionEvent.EVENT_CREATED],
        )

        existing_action, second_created = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
        )

        self.assertFalse(second_created)
        self.assertEqual(existing_action.id, action.id)
        self.assertEqual(PreparednessAction.objects.count(), 1)
        self.assertTrue(
            existing_action.events.filter(
                event_type=PreparednessActionEvent.EVENT_COMMENT,
                metadata__idempotency="existing_active_action_reused",
            ).exists()
        )

    def test_lifecycle_transitions_require_evidence_and_write_events(self):
        action, _ = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_RISK_SCORE,
            actor=self.admin_user,
            risk_score=self.risk_score,
        )

        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_ASSIGNED,
            assigned_to=self.supervisor_user,
            detail="Supervisor accepted ownership.",
        )
        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_ACKNOWLEDGED,
            detail="Acknowledged.",
        )
        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_IN_PROGRESS,
            detail="CHV follow-up started.",
        )
        with self.assertRaisesMessage(ValueError, "substantive detail"):
            transition_preparedness_action(
                action,
                actor=self.supervisor_user,
                status=PreparednessAction.STATUS_COMPLETED,
            )

        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_COMPLETED,
            completion_evidence={"summary": "Two households visited and counselled."},
            detail="Completed with field evidence.",
        )

        self.assertIsNotNone(action.acknowledged_at)
        self.assertIsNotNone(action.completed_at)
        self.assertEqual(action.completion_evidence["summary"], "Two households visited and counselled.")
        self.assertEqual(
            list(action.events.values_list("event_type", flat=True)),
            [
                PreparednessActionEvent.EVENT_CREATED,
                PreparednessActionEvent.EVENT_ASSIGNED,
                PreparednessActionEvent.EVENT_ACKNOWLEDGED,
                PreparednessActionEvent.EVENT_IN_PROGRESS,
                PreparednessActionEvent.EVENT_COMPLETED,
            ],
        )
        with self.assertRaisesMessage(ValueError, "cannot transition"):
            transition_preparedness_action(
                action,
                actor=self.supervisor_user,
                status=PreparednessAction.STATUS_CANCELLED,
                cancellation_reason="Trying to cancel a completed action.",
            )

    def test_same_status_reassignment_writes_assignment_event(self):
        action, _ = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_ASSIGNED,
            assigned_to=self.supervisor_user,
            due_at=timezone.now() + timedelta(hours=4),
        )

        action = transition_preparedness_action(
            action,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_ASSIGNED,
            assigned_to=self.admin_user,
            detail="Reassigned to admin lead.",
        )

        self.assertEqual(action.assigned_to, self.admin_user)
        assignment_event = action.events.filter(event_type=PreparednessActionEvent.EVENT_ASSIGNED).latest("created_at")
        self.assertEqual(assignment_event.metadata["old_assigned_to"], self.supervisor_user.id)
        self.assertEqual(assignment_event.metadata["assigned_to"], self.admin_user.id)
        self.assertTrue(assignment_event.metadata["assignment_changed"])

        action = transition_preparedness_action(
            action,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_ASSIGNED,
            assigned_to=None,
            assigned_to_provided=True,
            assigned_to_team="Ward response desk",
            detail="Moved to team ownership.",
        )

        self.assertIsNone(action.assigned_to)
        self.assertEqual(action.assigned_to_team, "Ward response desk")
        self.assertEqual(
            action.events.filter(event_type=PreparednessActionEvent.EVENT_ASSIGNED).count(),
            3,
        )

    def test_assignment_during_status_transition_writes_separate_assignment_event(self):
        action, _ = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_QUEUED,
            due_at=timezone.now() + timedelta(hours=4),
        )

        action = transition_preparedness_action(
            action,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_IN_PROGRESS,
            assigned_to_team="Ward response desk",
            detail="Started and assigned to ward desk.",
        )

        event_types = list(action.events.values_list("event_type", flat=True))
        self.assertEqual(
            event_types,
            [
                PreparednessActionEvent.EVENT_CREATED,
                PreparednessActionEvent.EVENT_IN_PROGRESS,
                PreparednessActionEvent.EVENT_ASSIGNED,
            ],
        )
        assignment_event = action.events.filter(event_type=PreparednessActionEvent.EVENT_ASSIGNED).latest("created_at")
        self.assertEqual(assignment_event.metadata["assigned_to_team"], "Ward response desk")
        self.assertTrue(assignment_event.metadata["paired_status_event"])

    def test_creation_normalizes_owner_due_and_assignment_event(self):
        action, created = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_QUEUED,
            assigned_to_team="Ward response desk",
        )

        self.assertTrue(created)
        self.assertEqual(action.status, PreparednessAction.STATUS_ASSIGNED)
        self.assertEqual(action.assigned_to_team, "Ward response desk")
        self.assertIsNotNone(action.due_at)
        self.assertEqual(action.sla_target_at, action.due_at)
        self.assertEqual(
            list(action.events.values_list("event_type", flat=True)),
            [PreparednessActionEvent.EVENT_CREATED, PreparednessActionEvent.EVENT_ASSIGNED],
        )

        unowned_action, _ = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            actor=self.admin_user,
            status=PreparednessAction.STATUS_QUEUED,
        )
        self.assertEqual(unowned_action.status, PreparednessAction.STATUS_QUEUED)
        self.assertIsNotNone(unowned_action.due_at)
        self.assertEqual(unowned_action.sla_target_at, unowned_action.due_at)

        with self.assertRaisesRegex(ValueError, "Draft preparedness actions cannot be assigned"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_MANUAL,
                actor=self.admin_user,
                status=PreparednessAction.STATUS_DRAFT,
                assigned_to_team="Draft owner",
            )

    def test_blocked_escalated_and_cancelled_paths_are_audited(self):
        action, _ = get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_WATER_TREATMENT_DISTRIBUTION,
            source_trigger_type=PreparednessAction.SOURCE_SYSTEM,
            source_trigger_ref="water-treatment:ledger-ward:2026-05-03",
            actor=self.admin_user,
            priority=PreparednessAction.PRIORITY_URGENT,
        )

        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_BLOCKED,
            detail="Distribution blocked by missing supply confirmation.",
        )
        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_ESCALATED,
            detail="Escalated to county operations.",
            escalation_metadata={"target": "county_ops"},
        )
        action = transition_preparedness_action(
            action,
            actor=self.supervisor_user,
            status=PreparednessAction.STATUS_CANCELLED,
            cancellation_reason="County operations replaced this with a consolidated dispatch.",
        )

        self.assertIsNotNone(action.escalated_at)
        self.assertIsNotNone(action.cancelled_at)
        self.assertEqual(action.escalation_metadata["target"], "county_ops")
        self.assertEqual(
            list(action.events.values_list("event_type", flat=True)),
            [
                PreparednessActionEvent.EVENT_CREATED,
                PreparednessActionEvent.EVENT_BLOCKED,
                PreparednessActionEvent.EVENT_ESCALATED,
                PreparednessActionEvent.EVENT_CANCELLED,
            ],
        )

    def test_api_create_is_idempotent_and_update_permissions_are_role_bound(self):
        self.client.force_authenticate(user=self.supervisor_user)
        payload = {
            "ward_id": self.ward.id,
            "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
            "source_trigger_type": PreparednessAction.SOURCE_ALERT,
            "alert_public_id": str(self.alert.public_id),
            "priority": PreparednessAction.PRIORITY_HIGH,
            "due_at": (timezone.now() + timedelta(hours=4)).isoformat(),
            "lineage_metadata": {"reason": "high_risk_alert_review"},
        }

        create_response = self.client.post(reverse("preparedness-action-list-create"), payload, format="json")
        self.assertEqual(create_response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["status"], PreparednessAction.STATUS_QUEUED)
        self.assertEqual(create_response.data["source_trigger_ref"], f"alert:{self.alert.public_id}")

        duplicate_response = self.client.post(reverse("preparedness-action-list-create"), payload, format="json")
        self.assertEqual(duplicate_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(duplicate_response.data["public_id"], create_response.data["public_id"])

        cross_ward_owner_response = self.client.post(
            reverse("preparedness-action-list-create"),
            {
                **payload,
                "status": PreparednessAction.STATUS_ASSIGNED,
                "assigned_to_id": self.analyst_user.id,
            },
            format="json",
        )
        self.assertEqual(cross_ward_owner_response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn("action ward", cross_ward_owner_response.data["detail"])

        detail_url = reverse("preparedness-action-detail", kwargs={"public_id": create_response.data["public_id"]})
        self.client.force_authenticate(user=self.analyst_user)
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, http_status.HTTP_200_OK)

        analyst_update_response = self.client.patch(
            detail_url,
            {"status": PreparednessAction.STATUS_IN_PROGRESS},
            format="json",
        )
        self.assertEqual(analyst_update_response.status_code, http_status.HTTP_403_FORBIDDEN)

        analyst_create_response = self.client.post(reverse("preparedness-action-list-create"), payload, format="json")
        self.assertEqual(analyst_create_response.status_code, http_status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.supervisor_user)
        in_progress_response = self.client.patch(
            detail_url,
            {"status": PreparednessAction.STATUS_IN_PROGRESS, "detail": "Verification started."},
            format="json",
        )
        self.assertEqual(in_progress_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(in_progress_response.data["status"], PreparednessAction.STATUS_IN_PROGRESS)

        missing_evidence_response = self.client.patch(
            detail_url,
            {"status": PreparednessAction.STATUS_COMPLETED},
            format="json",
        )
        self.assertEqual(missing_evidence_response.status_code, http_status.HTTP_400_BAD_REQUEST)

        boilerplate_evidence_response = self.client.patch(
            detail_url,
            {
                "status": PreparednessAction.STATUS_COMPLETED,
                "completion_evidence": {
                    "captured_via": "api",
                    "captured_at": timezone.now().isoformat(),
                },
            },
            format="json",
        )
        self.assertEqual(boilerplate_evidence_response.status_code, http_status.HTTP_400_BAD_REQUEST)

        complete_response = self.client.patch(
            detail_url,
            {
                "status": PreparednessAction.STATUS_COMPLETED,
                "completion_evidence": {
                    "field_report": "CHV verified no acute watery diarrhea cluster at the reported site."
                },
            },
            format="json",
        )
        self.assertEqual(complete_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(complete_response.data["status"], PreparednessAction.STATUS_COMPLETED)
        self.assertTrue(complete_response.data["completion_evidence"])

    def test_api_rejects_clearing_due_time_on_active_action(self):
        self.client.force_authenticate(user=self.supervisor_user)
        create_response = self.client.post(
            reverse("preparedness-action-list-create"),
            {
                "ward_id": self.ward.id,
                "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
                "source_trigger_type": PreparednessAction.SOURCE_MANUAL,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, http_status.HTTP_201_CREATED)
        self.assertIsNotNone(create_response.data["due_at"])

        clear_due_response = self.client.patch(
            reverse("preparedness-action-detail", kwargs={"public_id": create_response.data["public_id"]}),
            {"status": PreparednessAction.STATUS_QUEUED, "due_at": None},
            format="json",
        )

        self.assertEqual(clear_due_response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn("due time", clear_due_response.data["detail"])

    def test_api_list_filters_by_facility_and_chv_lineage(self):
        facility_action = PreparednessAction.objects.create(
            ward=self.ward,
            facility=self.facility,
            action_type=PreparednessAction.ACTION_FACILITY_ORS_REVIEW,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_HIGH,
        )
        chv_action = PreparednessAction.objects.create(
            ward=self.ward,
            chv=self.chv,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            assigned_to_team="Ward CHV team",
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
        )
        completed_action = PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            completion_evidence={"summary": "Closed after field verification."},
            completed_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.supervisor_user)
        facility_response = self.client.get(
            reverse("preparedness-action-list-create"),
            {"facility_id": self.facility.id},
        )
        chv_response = self.client.get(
            reverse("preparedness-action-list-create"),
            {"chv_id": self.chv.id},
        )
        active_status_response = self.client.get(
            reverse("preparedness-action-list-create"),
            {"status": ",".join([PreparednessAction.STATUS_QUEUED, PreparednessAction.STATUS_ASSIGNED])},
        )

        self.assertEqual(facility_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(facility_response.data["count"], 1)
        self.assertEqual(facility_response.data["results"][0]["public_id"], str(facility_action.public_id))
        self.assertEqual(chv_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(chv_response.data["count"], 1)
        self.assertEqual(chv_response.data["results"][0]["public_id"], str(chv_action.public_id))
        self.assertEqual(active_status_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(active_status_response.data["count"], 3)
        self.assertNotIn(
            str(completed_action.public_id),
            {row["public_id"] for row in active_status_response.data["results"]},
        )

    def test_service_rejects_cross_ward_non_admin_assignee(self):
        with self.assertRaisesRegex(ValueError, "action ward"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_MANUAL,
                actor=self.admin_user,
                status=PreparednessAction.STATUS_ASSIGNED,
                assigned_to=self.analyst_user,
                due_at=timezone.now() + timedelta(hours=4),
            )

    def test_service_rejects_mismatched_risk_score_model_run_lineage(self):
        other_model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="ledger-other-v1",
            status=ModelRun.STATUS_SUCCESS,
            completed_at=timezone.now(),
        )

        with self.assertRaisesRegex(ValueError, "model run lineage"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_RISK_SCORE,
                actor=self.admin_user,
                risk_score=self.risk_score,
                model_run=other_model_run,
                due_at=timezone.now() + timedelta(hours=4),
            )

    def test_service_rejects_source_and_decision_policy_lineage_gaps(self):
        with self.assertRaisesRegex(ValueError, "linked alert"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_ALERT,
                actor=self.admin_user,
            )

        with self.assertRaisesRegex(ValueError, "source reference or lineage metadata"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_SYSTEM,
                actor=self.admin_user,
            )

        with self.assertRaisesRegex(ValueError, "decision policy lineage"):
            get_or_create_preparedness_action(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_RISK_SCORE,
                actor=self.admin_user,
                risk_score=self.risk_score,
                decision_policy_version="wrong-policy",
            )

    def test_alert_workflow_trigger_creates_field_verification_action_without_delivery_mutation(self):
        workflow = sync_alert_workflow_for_ward(self.ward, record_event=False)
        self.assertEqual(workflow.status, AlertWorkflowState.STATUS_DELIVERED)

        self.client.force_authenticate(user=self.supervisor_user)
        response = self.client.post(
            reverse("alert-workflow-preparedness-action-create", kwargs={"public_id": workflow.public_id}),
            {
                "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
                "lineage_metadata": {"operator_reason": "high-risk alert review"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data["action_type"], PreparednessAction.ACTION_FIELD_VERIFICATION)
        self.assertEqual(response.data["source_trigger_type"], PreparednessAction.SOURCE_ALERT_WORKFLOW)
        self.assertEqual(response.data["source_trigger_ref"], f"alert_workflow:{workflow.public_id}")
        self.assertEqual(response.data["alert_workflow_public_id"], str(workflow.public_id))
        self.assertEqual(response.data["risk_score"], self.risk_score.id)
        self.assertEqual(response.data["decision_policy_version"], "policy-v1")
        self.assertIsNotNone(response.data["due_at"])

        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, Alert.STATUS_DELIVERED)

        duplicate_response = self.client.post(
            reverse("alert-workflow-preparedness-action-create", kwargs={"public_id": workflow.public_id}),
            {"action_type": PreparednessAction.ACTION_FIELD_VERIFICATION},
            format="json",
        )
        self.assertEqual(duplicate_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(duplicate_response.data["public_id"], response.data["public_id"])
        self.assertEqual(
            PreparednessAction.objects.filter(
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_ALERT_WORKFLOW,
                source_trigger_ref=f"alert_workflow:{workflow.public_id}",
            ).count(),
            1,
        )

    def test_alert_trigger_creates_household_prevention_action(self):
        self.client.force_authenticate(user=self.supervisor_user)
        response = self.client.post(
            reverse("alert-preparedness-action-create", kwargs={"pk": self.alert.id}),
            {
                "action_type": PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
                "priority": PreparednessAction.PRIORITY_MEDIUM,
                "notes": "Operator chose prevention-message follow-up after delivery review.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data["action_type"], PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE)
        self.assertEqual(response.data["source_trigger_type"], PreparednessAction.SOURCE_ALERT)
        self.assertEqual(response.data["source_trigger_ref"], f"alert:{self.alert.public_id}")
        self.assertEqual(response.data["alert_public_id"], str(self.alert.public_id))
        self.assertEqual(response.data["risk_score"], self.risk_score.id)

        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, Alert.STATUS_DELIVERED)

    def test_chv_coverage_request_trigger_creates_chv_follow_up_with_alert_and_chv_lineage(self):
        coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_IN_PROGRESS,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
            reason="Alert-linked CHV coverage needed.",
            requested_chv_count=1,
            assigned_to_user=self.supervisor_user,
            expected_response_by=timezone.now() + timedelta(hours=4),
        )
        CHVCoverageRequestAlertLink.objects.create(
            coverage_request=coverage_request,
            alert=self.alert,
            linked_by=self.supervisor_user,
        )
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.supervisor_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )

        self.client.force_authenticate(user=self.supervisor_user)
        response = self.client.post(
            reverse("chv-coverage-request-preparedness-action-create", kwargs={"public_id": coverage_request.public_id}),
            {"action_type": PreparednessAction.ACTION_CHV_FOLLOW_UP},
            format="json",
        )

        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data["source_trigger_type"], PreparednessAction.SOURCE_CHV_COVERAGE_REQUEST)
        self.assertEqual(response.data["source_trigger_ref"], f"chv_coverage_request:{coverage_request.public_id}")
        self.assertEqual(response.data["chv_coverage_request_public_id"], str(coverage_request.public_id))
        self.assertEqual(response.data["alert_public_id"], str(self.alert.public_id))
        self.assertEqual(response.data["chv"], self.chv.id)
        self.assertEqual(response.data["risk_score"], self.risk_score.id)

        duplicate_response = self.client.post(
            reverse("chv-coverage-request-preparedness-action-create", kwargs={"public_id": coverage_request.public_id}),
            {"action_type": PreparednessAction.ACTION_CHV_FOLLOW_UP},
            format="json",
        )
        self.assertEqual(duplicate_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(duplicate_response.data["public_id"], response.data["public_id"])

        invalid_response = self.client.post(
            reverse("chv-coverage-request-preparedness-action-create", kwargs={"public_id": coverage_request.public_id}),
            {"action_type": PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_facility_review_and_escalation_triggers_create_distinct_actions(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_HIGH,
            reason_codes=["ors_stock_pressure"],
            created_by=self.supervisor_user,
        )
        escalation = FacilityReadinessEscalation.objects.create(
            review=review,
            facility=self.facility,
            ward=self.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_HIGH,
            reason="County support needed for ORS replenishment.",
            created_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.supervisor_user)
        review_response = self.client.post(
            reverse("facility-readiness-review-preparedness-action-create", kwargs={"public_id": review.public_id}),
            {"action_type": PreparednessAction.ACTION_FACILITY_ORS_REVIEW},
            format="json",
        )
        self.assertEqual(review_response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(review_response.data["source_trigger_type"], PreparednessAction.SOURCE_FACILITY_READINESS_REVIEW)
        self.assertEqual(review_response.data["source_trigger_ref"], f"facility_readiness_review:{review.public_id}")
        self.assertEqual(review_response.data["facility_readiness_review_public_id"], str(review.public_id))
        self.assertEqual(review_response.data["facility"], self.facility.id)

        escalation_response = self.client.post(
            reverse(
                "facility-readiness-escalation-preparedness-action-create",
                kwargs={"public_id": escalation.public_id},
            ),
            {"action_type": PreparednessAction.ACTION_COUNTY_ESCALATION},
            format="json",
        )
        self.assertEqual(escalation_response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(escalation_response.data["source_trigger_type"], PreparednessAction.SOURCE_FACILITY_ESCALATION)
        self.assertEqual(escalation_response.data["source_trigger_ref"], f"facility_escalation:{escalation.public_id}")
        self.assertEqual(escalation_response.data["facility_escalation_public_id"], str(escalation.public_id))
        self.assertEqual(escalation_response.data["priority"], PreparednessAction.PRIORITY_URGENT)

        duplicate_escalation_response = self.client.post(
            reverse(
                "facility-readiness-escalation-preparedness-action-create",
                kwargs={"public_id": escalation.public_id},
            ),
            {"action_type": PreparednessAction.ACTION_COUNTY_ESCALATION},
            format="json",
        )
        self.assertEqual(duplicate_escalation_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(duplicate_escalation_response.data["public_id"], escalation_response.data["public_id"])

    def test_preparedness_action_audit_passes_for_clean_live_and_seeded_demo_context(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        seeded_model_run = ModelRun.objects.create(
            algorithm_name="seed-demo-baseline",
            model_version="audit-seeded-demo-v1",
            status=ModelRun.STATUS_SUCCESS,
            metadata={
                "seeded": True,
                "seeded_non_production": True,
                "promotion_target": "demo_only",
                "alert_eligible": False,
            },
            completed_at=timezone.now(),
        )
        seeded_risk_score = RiskScore.objects.create(
            ward=self.other_ward,
            model_run=seeded_model_run,
            score=0.89,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=12,
            source=RiskScore.SOURCE_MODEL,
            model_version=seeded_model_run.model_version,
        )
        Alert.objects.create(
            ward=self.other_ward,
            risk_score=seeded_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Seeded demo alert should not be treated as live promoted.",
            status=Alert.STATUS_DELIVERED,
        )

        audit = build_preparedness_action_ledger_audit()

        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(audit["record_totals"]["high_risk_promoted_alerts"], 1)
        self.assertTrue(all(item["status"] == "pass" for item in audit["audit_checks"]))

    def test_preparedness_action_audit_rejects_cancelled_only_alert_follow_up(self):
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref=f"alert:{self.alert.public_id}",
            alert=self.alert,
            risk_score=self.risk_score,
            status=PreparednessAction.STATUS_CANCELLED,
            priority=PreparednessAction.PRIORITY_HIGH,
            cancelled_at=timezone.now(),
            cancellation_reason="Operator cancelled without replacement.",
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["high_risk_promoted_alerts_without_action_tasks"]["status"], "fail")
        self.assertEqual(
            checks["high_risk_promoted_alerts_without_action_tasks"]["evidence"]["missing_action_alert_count"],
            1,
        )

    def test_preparedness_action_audit_detects_duplicate_active_actions_when_source_ref_is_blank(self):
        for owner in [None, self.supervisor_user]:
            PreparednessAction.objects.create(
                ward=self.ward,
                action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
                source_trigger_type=PreparednessAction.SOURCE_ALERT,
                source_trigger_ref="",
                alert=self.alert,
                risk_score=self.risk_score,
                status=PreparednessAction.STATUS_QUEUED,
                priority=PreparednessAction.PRIORITY_HIGH,
                assigned_to=owner,
            )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}
        duplicate_check = checks["duplicate_active_actions_for_same_source_trigger"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["high_risk_promoted_alerts_without_action_tasks"]["status"], "pass")
        self.assertEqual(duplicate_check["status"], "fail")
        self.assertEqual(duplicate_check["evidence"]["duplicate_group_count"], 1)
        self.assertEqual(
            duplicate_check["evidence"]["duplicate_groups"][0]["normalized_source_trigger_ref"],
            f"alert:{self.alert.public_id}",
        )

    def test_preparedness_action_audit_rejects_boilerplate_only_completion_evidence(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            completed_at=timezone.now(),
            completion_evidence={
                "captured_via": "api",
                "captured_at": timezone.now().isoformat(),
            },
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["completed_actions_without_required_evidence"]["status"], "fail")
        self.assertEqual(
            checks["completed_actions_without_required_evidence"]["evidence"]["completed_missing_evidence_count"],
            1,
        )

    def test_preparedness_action_audit_flags_cross_ward_assigned_owner(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            assigned_to=self.analyst_user,
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}
        detached_check = checks["actions_detached_from_ward_or_source_lineage"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(detached_check["status"], "fail")
        self.assertIn(
            "assigned_owner_ward_mismatch",
            detached_check["evidence"]["detached_or_cross_ward_actions"][0]["lineage_gaps"],
        )

    def test_preparedness_action_audit_flags_missing_lifecycle_events(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            completed_at=timezone.now(),
            completion_evidence={"summary": "Surveillance follow-up confirmed."},
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}
        lifecycle_check = checks["lifecycle_events_are_auditable"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(lifecycle_check["status"], "fail")
        self.assertIn(
            "missing_created_event",
            lifecycle_check["evidence"]["lifecycle_gap_actions"][0]["lifecycle_gaps"],
        )
        self.assertIn(
            "missing_completed_event",
            lifecycle_check["evidence"]["lifecycle_gap_actions"][0]["lifecycle_gaps"],
        )

    def test_preparedness_action_audit_flags_mismatched_prediction_lineage(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        other_model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="ledger-mismatched-v1",
            status=ModelRun.STATUS_SUCCESS,
            completed_at=timezone.now(),
        )
        mismatched_action = PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            risk_score=self.risk_score,
            model_run=other_model_run,
            decision_policy_version="wrong-policy",
        )
        PreparednessActionEvent.objects.create(
            preparedness_action=mismatched_action,
            actor=self.admin_user,
            event_type=PreparednessActionEvent.EVENT_CREATED,
            new_status=PreparednessAction.STATUS_QUEUED,
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}
        detached_check = checks["actions_detached_from_ward_or_source_lineage"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(detached_check["status"], "fail")
        self.assertIn(
            "risk_score_model_run_mismatch",
            detached_check["evidence"]["detached_or_cross_ward_actions"][0]["lineage_gaps"],
        )
        self.assertIn(
            "decision_policy_version_mismatch",
            detached_check["evidence"]["detached_or_cross_ward_actions"][0]["lineage_gaps"],
        )

    def test_preparedness_action_audit_flags_missing_due_sla_and_assignment_events(self):
        get_or_create_preparedness_action(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            actor=self.admin_user,
            alert=self.alert,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() + timedelta(hours=4),
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            assigned_to_team="Ward response desk",
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}
        due_check = checks["active_actions_have_due_and_sla_targets"]
        assignment_check = checks["assignment_state_is_auditable"]

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(due_check["status"], "fail")
        self.assertIn(
            "missing_due_at",
            due_check["evidence"]["missing_due_or_sla_actions"][0]["due_sla_gaps"],
        )
        self.assertIn(
            "missing_sla_target_at",
            due_check["evidence"]["missing_due_or_sla_actions"][0]["due_sla_gaps"],
        )
        self.assertEqual(assignment_check["status"], "fail")
        self.assertIn(
            "owner_without_assignment_event",
            assignment_check["evidence"]["assignment_gap_actions"][0]["assignment_gaps"],
        )
        self.assertIn(
            "draft_or_queued_action_has_owner",
            assignment_check["evidence"]["assignment_gap_actions"][0]["assignment_gaps"],
        )

    def test_preparedness_action_audit_flags_hostile_ledger_gaps(self):
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_CHV_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_RISK_SCORE,
            source_trigger_ref=f"risk_score:{self.risk_score.id}:overdue",
            risk_score=self.risk_score,
            status=PreparednessAction.STATUS_IN_PROGRESS,
            priority=PreparednessAction.PRIORITY_HIGH,
            due_at=timezone.now() - timedelta(hours=2),
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            status=PreparednessAction.STATUS_COMPLETED,
            priority=PreparednessAction.PRIORITY_HIGH,
            completed_at=timezone.now() - timedelta(minutes=10),
            completion_evidence={},
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref="alert:duplicate-source",
            alert=self.alert,
            risk_score=self.risk_score,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_HIGH,
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref=" alert:duplicate-source ",
            alert=self.alert,
            risk_score=self.risk_score,
            status=PreparednessAction.STATUS_ASSIGNED,
            priority=PreparednessAction.PRIORITY_HIGH,
            assigned_to=self.supervisor_user,
        )
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            source_trigger_ref="",
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_MEDIUM,
        )

        audit = build_preparedness_action_ledger_audit()
        checks = {item["id"]: item for item in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["high_risk_promoted_alerts_without_action_tasks"]["status"], "pass")
        self.assertEqual(checks["overdue_actions_without_escalation"]["status"], "fail")
        self.assertEqual(checks["completed_actions_without_required_evidence"]["status"], "fail")
        self.assertEqual(checks["duplicate_active_actions_for_same_source_trigger"]["status"], "fail")
        self.assertEqual(checks["actions_detached_from_ward_or_source_lineage"]["status"], "fail")

    def test_preparedness_action_audit_command_outputs_json_and_strict_failure(self):
        PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_ALERT,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_HIGH,
        )

        stdout = StringIO()
        call_command("audit_preparedness_action_ledger", "--format=json", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["overall_status"], "fail")
        self.assertEqual(payload["schema_version"], "preparedness-action-ledger-audit-v1")
        with self.assertRaises(CommandError):
            call_command("audit_preparedness_action_ledger", "--strict", stdout=StringIO())
