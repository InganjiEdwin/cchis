from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from risk.ml.registry import ensure_registry_entry_for_promoted_run
from risk.providers import DeliveryResult

from .models import (
    Alert,
    CHV,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    FacilityContact,
    FacilityReadinessReview,
    FacilityReadinessUpdateRequest,
    HealthFacility,
    ModelRun,
    RiskScore,
    Ward,
)
from .services import (
    MESSAGE_PURPOSE_HOUSEHOLD_PREVENTION,
    assert_contact_message_allowed,
    contact_reference_for_chv,
    contact_reference_for_facility_contact,
    create_alerts_for_riskscore,
    record_contact_preference,
)


class ContactPreferenceGovernanceTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.ward = Ward.objects.create(
            name="Privacy Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.88,
            is_active=True,
        )
        self.admin_user = User.objects.create_user(
            username="privacy_admin",
            password=self.password,
            email="privacy_admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.chv = CHV.objects.create(
            name="Privacy CHV",
            phone_number="+254700111001",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        self.facility = HealthFacility.objects.create(
            name="Privacy Dispensary",
            facility_code="PRIV-FAC-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254720111001",
        )
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="privacy-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=5,
            feature_schema_version="baseline-v1",
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases"],
            metadata={
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "alert_eligible": True,
            },
            completed_at=timezone.now(),
        )
        ensure_registry_entry_for_promoted_run(
            model_run=self.model_run,
            owner="message-governance",
            promoted_by="contact-preference-test",
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.88,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=140.0,
            flood_indicator=0.81,
            predicted_cases=18,
            source=RiskScore.SOURCE_MODEL,
            model_version="privacy-v1",
        )

    def test_household_message_requires_consent_or_audited_emergency_override(self):
        with self.assertRaisesMessage(ValueError, "Household messaging requires consent"):
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="0700111222",
                actor=self.admin_user,
            )

        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_BLOCKED_CONSENT_REQUIRED,
                phone_number="+254700111222",
            ).exists()
        )

        preference = record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="0700111222",
            consent_status=ContactPreference.CONSENT_GRANTED,
            source="household_sms_consent",
            source_reference="consent-form-1",
            recorded_by=self.admin_user,
        )
        self.assertEqual(
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="+254700111222",
                actor=self.admin_user,
            ),
            preference,
        )

        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700111222",
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="sms_opt_out",
            source_reference="reply-stop-1",
            recorded_by=self.admin_user,
        )
        with self.assertRaisesMessage(ValueError, "opted out"):
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="+254700111222",
                actor=self.admin_user,
            )

        assert_contact_message_allowed(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700111222",
            actor=self.admin_user,
            emergency_override=True,
            override_reason="urgent ward public health response",
        )
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED,
                phone_number="+254700111222",
                reason="urgent ward public health response",
            ).exists()
        )

    def test_household_message_can_use_approved_lawful_basis_but_still_respects_opt_out(self):
        preference = record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="0700111444",
            consent_status=ContactPreference.CONSENT_UNKNOWN,
            opt_out_status=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
            source="county_public_health_register",
            source_reference="lawful-basis-household-1",
            recorded_by=self.admin_user,
            metadata={
                "lawful_basis": "public_health_response",
                "lawful_basis_approved": True,
                "lawful_basis_reference": "county-cmo-approval-1",
            },
        )

        self.assertEqual(
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="+254700111444",
                actor=self.admin_user,
                audit_allowed=True,
                message_purpose=MESSAGE_PURPOSE_HOUSEHOLD_PREVENTION,
            ),
            preference,
        )
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_ALLOWED,
                phone_number="+254700111444",
                metadata__lawful_basis_approved=True,
                metadata__message_purpose=MESSAGE_PURPOSE_HOUSEHOLD_PREVENTION,
            ).exists()
        )

        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700111444",
            consent_status=ContactPreference.CONSENT_UNKNOWN,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="sms_opt_out",
            source_reference="reply-stop-lawful-basis",
            recorded_by=self.admin_user,
            metadata={
                "lawful_basis": "public_health_response",
                "lawful_basis_approved": True,
                "lawful_basis_reference": "county-cmo-approval-1",
            },
        )

        with self.assertRaisesMessage(ValueError, "opted out"):
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="+254700111444",
                actor=self.admin_user,
                message_purpose=MESSAGE_PURPOSE_HOUSEHOLD_PREVENTION,
            )

    def test_contact_preference_api_records_preference_and_audit_event(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("contact-preference-list-create"),
            {
                "audience_type": ContactPreference.AUDIENCE_HOUSEHOLD,
                "channel": ContactPreference.CHANNEL_SMS,
                "phone_number": "0700111333",
                "consent_status": ContactPreference.CONSENT_GRANTED,
                "opt_out_status": ContactPreference.OPT_OUT_NOT_OPTED_OUT,
                "source": "household_sms_consent",
                "source_reference": "consent-form-2",
                "metadata": {"lawful_basis": "public_health_response"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["phone_number"], "+254700111333")
        preference = ContactPreference.objects.get(public_id=response.data["public_id"])
        self.assertEqual(preference.recorded_by, self.admin_user)
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                preference=preference,
                action=ContactPreferenceAuditEvent.ACTION_RECORDED,
                actor=self.admin_user,
            ).exists()
        )

    def test_contact_preference_rejects_invalid_explicit_phone_identifier(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("contact-preference-list-create"),
            {
                "audience_type": ContactPreference.AUDIENCE_HOUSEHOLD,
                "channel": ContactPreference.CHANNEL_SMS,
                "phone_number": "caregiver-one",
                "consent_status": ContactPreference.CONSENT_GRANTED,
                "source": "household_sms_consent",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data)
        self.assertEqual(ContactPreference.objects.count(), 0)

        with self.assertRaisesMessage(ValueError, "valid Kenyan mobile numbers"):
            assert_contact_message_allowed(
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="caregiver-one",
                actor=self.admin_user,
            )

    @patch("risk.services.send_sms")
    def test_chv_message_respects_opt_out_before_delivery(self, mock_send_sms):
        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_CHV,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number=self.chv.phone_number,
            contact_reference=contact_reference_for_chv(self.chv),
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="chv_sms_opt_out",
            source_reference="reply-stop-chv",
            recorded_by=self.admin_user,
        )
        self.client.force_authenticate(self.admin_user)

        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"):
            response = self.client.post(
                reverse("chv-message-list-create", args=[self.chv.public_id]),
                {"message_body": "Please confirm ward readiness.", "channel": ContactPreference.CHANNEL_SMS},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CHVMessage.objects.count(), 0)
        mock_send_sms.assert_not_called()
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT,
                contact_reference=contact_reference_for_chv(self.chv),
            ).exists()
        )

    @patch("risk.services.send_sms")
    def test_chv_message_emergency_override_is_audited(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="sms-pref-override",
            error="",
            provider="stub",
        )
        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_CHV,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number=self.chv.phone_number,
            contact_reference=contact_reference_for_chv(self.chv),
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="chv_sms_opt_out",
            source_reference="reply-stop-chv",
            recorded_by=self.admin_user,
        )
        self.client.force_authenticate(self.admin_user)

        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"):
            response = self.client.post(
                reverse("chv-message-list-create", args=[self.chv.public_id]),
                {
                    "message_body": "Please confirm ward readiness.",
                    "channel": ContactPreference.CHANNEL_SMS,
                    "emergency_override": True,
                    "override_reason": "urgent ward public health response",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CHVMessage.objects.count(), 1)
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_EMERGENCY_OVERRIDE_USED,
                contact_reference=contact_reference_for_chv(self.chv),
                reason="urgent ward public health response",
            ).exists()
        )

    def test_facility_update_request_respects_contact_opt_out(self):
        contact = FacilityContact.objects.create(
            facility=self.facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720111001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-privacy",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )
        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_FACILITY_CONTACT,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number=contact.phone,
            contact_reference=contact_reference_for_facility_contact(contact),
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="facility_contact_opt_out",
            source_reference="facility-stop-1",
            recorded_by=self.admin_user,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Please update ORS and staffing status."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 0)
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT,
                contact_reference=contact_reference_for_facility_contact(contact),
            ).exists()
        )

    def test_facility_update_request_records_audience_governance_metadata(self):
        contact = FacilityContact.objects.create(
            facility=self.facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720111002",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-governance",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Please update ORS and staffing status."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        update_request = FacilityReadinessUpdateRequest.objects.get(public_id=response.data["public_id"])
        self.assertEqual(update_request.contact, contact)
        self.assertEqual(update_request.governance_metadata["schema_version"], "message-audience-governance-phase-2-v1")
        self.assertTrue(update_request.governance_metadata["audience_decision"]["allowed"])
        self.assertEqual(
            update_request.governance_metadata["audience_decision"]["audience_type"],
            ContactPreference.AUDIENCE_FACILITY_CONTACT,
        )
        self.assertTrue(update_request.governance_metadata["audience_scope"]["facility_contact_verified"])

    def test_alert_sms_creation_skips_chv_opted_out_of_direct_messaging(self):
        record_contact_preference(
            audience_type=ContactPreference.AUDIENCE_CHV,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number=self.chv.phone_number,
            contact_reference=contact_reference_for_chv(self.chv),
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="chv_sms_opt_out",
            source_reference="reply-stop-alert",
            recorded_by=self.admin_user,
        )

        alerts = create_alerts_for_riskscore(self.risk_score, send_sms_enabled=True)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].channel, Alert.CHANNEL_DASHBOARD)
        self.assertFalse(Alert.objects.filter(channel=Alert.CHANNEL_SMS).exists())
        self.assertTrue(
            ContactPreferenceAuditEvent.objects.filter(
                action=ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT,
                contact_reference=contact_reference_for_chv(self.chv),
                metadata__workflow="risk_alert_sms",
            ).exists()
        )
