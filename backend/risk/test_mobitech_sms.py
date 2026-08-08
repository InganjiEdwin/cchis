import io
import json
import urllib.error
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from risk.models import Alert, AlertDeliveryEvent, RiskScore, Ward
from risk.providers import (
    AfricasTalkingSmsProvider,
    MobitechSmsProvider,
    ParkedAfricasTalkingSmsProvider,
    StubSmsProvider,
    get_sms_provider,
)
from risk.services import deliver_alert
from risk.sms_delivery import process_mobitech_delivery_callback
from risk.tasks import trigger_alerts_task


class MobitechSmsTests(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Mobitech Test Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.9,
            is_active=True,
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.9,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=8,
            model_version="mobitech-test-v1",
        )

    @override_settings(SMS_PROVIDER="mobitech", AFRICAS_TALKING_ENABLED=False)
    def test_active_route_selects_mobitech_and_africas_talking_is_parked(self):
        self.assertIsInstance(get_sms_provider(), MobitechSmsProvider)
        self.assertIsInstance(get_sms_provider("africastalking"), ParkedAfricasTalkingSmsProvider)
        self.assertTrue(issubclass(AfricasTalkingSmsProvider, object))

    @override_settings(
        SMS_PROVIDER="mobitech",
        MOBITECH_API_URL="https://mobitech.example.test/sms/sendmultiple",
        MOBITECH_API_KEY="fixture-api-key",
        MOBITECH_SENDER_ID="CCHIS",
        MOBITECH_SERVICE_ID="0",
        MOBITECH_HTTP_TIMEOUT_SECONDS=7,
    )
    @patch("risk.providers._post_mobitech_json")
    def test_mobitech_request_matches_linda_payload_and_normalizes_kenyan_number(self, post_json):
        post_json.return_value = (
            200,
            json.dumps(
                {
                    "status_code": 1000,
                    "status_desc": "Success",
                    "schedule_details": [
                        {"message_id": 30934623, "schedule_status": "1"},
                    ],
                }
            ),
        )

        result = get_sms_provider().send(
            "+254 712-345-678",
            "Test alert body",
            idempotency_key="4ab6a311-1d75-4fd0-8f04-9bbf8f9e0f29",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.external_id, "30934623")
        self.assertEqual(result.provider_acceptance_status, "accepted")
        self.assertEqual(post_json.call_args.args[0], "https://mobitech.example.test/sms/sendmultiple")
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["serviceId"], "0")
        self.assertEqual(payload["shortcode"], "CCHIS")
        self.assertEqual(payload["messages"][0]["mobile"], "254712345678")
        self.assertEqual(payload["messages"][0]["message"], "Test alert body")
        self.assertEqual(payload["messages"][0]["client_ref"], "4ab6a311-1d75-4fd0-8f04-9bbf8f9e0f29")
        self.assertEqual(post_json.call_args.kwargs["api_key"], "fixture-api-key")
        self.assertEqual(post_json.call_args.kwargs["timeout_seconds"], 7)
        self.assertNotIn("712345678", json.dumps(result.request_metadata))
        self.assertNotIn("Test alert body", json.dumps(result.request_metadata))

    @override_settings(
        MOBITECH_API_URL="https://mobitech.example.test/sms/sendmultiple",
        MOBITECH_API_KEY="",
        MOBITECH_SENDER_ID="CCHIS",
    )
    def test_invalid_mobitech_credentials_and_numbers_fail_without_network(self):
        missing_credentials = MobitechSmsProvider().send("0712345678", "Alert")
        self.assertFalse(missing_credentials.success)
        self.assertEqual(missing_credentials.error_code, "provider_not_configured")

        with override_settings(MOBITECH_API_KEY="fixture-api-key"):
            with patch("risk.providers._post_mobitech_json") as post_json:
                invalid_number = MobitechSmsProvider().send("020-123-456", "Alert")
        self.assertFalse(invalid_number.success)
        self.assertEqual(invalid_number.error_code, "invalid_phone_number")
        post_json.assert_not_called()

    @override_settings(
        MOBITECH_API_URL="https://mobitech.example.test/sms/sendmultiple",
        MOBITECH_API_KEY="fixture-api-key",
        MOBITECH_SENDER_ID="CCHIS",
    )
    @patch("risk.providers._post_mobitech_json")
    def test_provider_logs_and_response_metadata_do_not_expose_secrets_or_message(self, post_json):
        post_json.return_value = (
            200,
            json.dumps(
                {
                    "status_code": 1000,
                    "status_desc": "accepted",
                    "schedule_details": [{"message_id": "provider-1", "schedule_status": "1"}],
                }
            ),
        )
        with self.assertLogs("risk.alerts", level="INFO") as captured:
            result = MobitechSmsProvider().send(
                "0712345678",
                "Private message body",
                idempotency_key="private-key",
            )

        output = "\n".join(captured.output)
        self.assertNotIn("fixture-api-key", output)
        self.assertNotIn("0712345678", output)
        self.assertNotIn("Private message body", output)
        self.assertNotIn("Private message body", json.dumps(result.response_metadata))

    @override_settings(
        MOBITECH_API_URL="https://mobitech.example.test/sms/sendmultiple",
        MOBITECH_API_KEY="fixture-api-key",
        MOBITECH_SENDER_ID="CCHIS",
    )
    @patch("risk.providers._post_mobitech_json")
    def test_only_http_5xx_is_retryable_and_error_payload_is_not_retained(self, post_json):
        post_json.side_effect = urllib.error.HTTPError(
            "https://mobitech.example.test/sms/sendmultiple",
            503,
            "provider unavailable",
            {},
            io.BytesIO(b"private provider response"),
        )

        result = MobitechSmsProvider().send("0712345678", "Private message body")

        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_code, "http_503")
        self.assertNotIn("private provider response", json.dumps(result.response_metadata))

        post_json.reset_mock()
        post_json.side_effect = urllib.error.HTTPError(
            "https://mobitech.example.test/sms/sendmultiple",
            401,
            "unauthorized",
            {},
            io.BytesIO(b"private auth response"),
        )
        permanent = MobitechSmsProvider().send("0712345678", "Private message body")

        self.assertFalse(permanent.success)
        self.assertFalse(permanent.retryable)
        self.assertEqual(permanent.error_code, "http_401")
        self.assertNotIn("private auth response", json.dumps(permanent.response_metadata))

    @override_settings(SMS_PROVIDER="mobitech")
    @patch("risk.services.send_sms")
    def test_provider_acceptance_and_message_id_are_persisted_without_claiming_delivery(self, send_sms):
        accepted_at = timezone.now()
        send_sms.return_value = self._accepted_result(accepted_at=accepted_at)
        alert = self._alert()

        deliver_alert(alert)
        alert.refresh_from_db()

        self.assertEqual(alert.status, Alert.STATUS_QUEUED)
        self.assertEqual(alert.delivery_backend, "mobitech")
        self.assertEqual(alert.provider_message_id, "mobitech-message-1")
        self.assertEqual(alert.external_id, "mobitech-message-1")
        self.assertEqual(alert.provider_acceptance_status, Alert.PROVIDER_ACCEPTANCE_ACCEPTED)
        self.assertEqual(alert.provider_delivery_status, Alert.PROVIDER_DELIVERY_PENDING)
        self.assertEqual(alert.provider_accepted_at, accepted_at)
        self.assertEqual(alert.attempt_count, 1)
        self.assertTrue(alert.provider_request_metadata)
        self.assertTrue(alert.provider_response_metadata)
        self.assertTrue(alert.idempotency_key)
        send_sms.assert_called_once()
        self.assertEqual(send_sms.call_args.kwargs["idempotency_key"], str(alert.idempotency_key))

    @override_settings(MOBITECH_DELIVERY_CALLBACK_TOKEN="callback-token")
    def test_callback_reconciliation_is_idempotent_and_updates_final_delivery(self):
        alert = self._alert(
            status=Alert.STATUS_QUEUED,
            provider_message_id="mobitech-message-1",
            external_id="mobitech-message-1",
            provider_acceptance_status=Alert.PROVIDER_ACCEPTANCE_ACCEPTED,
        )
        payload = {
            "event_id": "mobitech-event-1",
            "message_id": "mobitech-message-1",
            "status": "delivered",
            "statusDescription": "Delivered",
            "subscriber": "254712345678",
        }

        first = APIClient().post(
            reverse("mobitech-delivery-callback"),
            payload,
            format="json",
            HTTP_X_MOBITECH_CALLBACK_TOKEN="callback-token",
        )
        second = APIClient().post(
            reverse("mobitech-delivery-callback"),
            payload,
            format="json",
            HTTP_X_MOBITECH_CALLBACK_TOKEN="callback-token",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(AlertDeliveryEvent.objects.count(), 1)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(alert.provider_delivery_status, Alert.PROVIDER_DELIVERY_DELIVERED)
        self.assertTrue(alert.callback_payload_hash)
        self.assertNotIn("254712345678", json.dumps(AlertDeliveryEvent.objects.get().sanitized_payload))

        late_failure = process_mobitech_delivery_callback(
            {
                "event_id": "mobitech-event-2",
                "message_id": "mobitech-message-1",
                "status": "failed",
            }
        )
        self.assertEqual(late_failure["status"], "processed")
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(alert.provider_delivery_status, Alert.PROVIDER_DELIVERY_DELIVERED)

    @override_settings(MOBITECH_DELIVERY_CALLBACK_TOKEN="callback-token")
    def test_invalid_callback_token_does_not_mutate_delivery_state(self):
        self._alert(
            provider_message_id="mobitech-message-1",
            external_id="mobitech-message-1",
            provider_acceptance_status=Alert.PROVIDER_ACCEPTANCE_ACCEPTED,
        )
        response = APIClient().post(
            reverse("mobitech-delivery-callback"),
            {"message_id": "mobitech-message-1", "status": "delivered"},
            format="json",
            HTTP_X_MOBITECH_CALLBACK_TOKEN="wrong-token",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AlertDeliveryEvent.objects.exists())

    @override_settings(SMS_PROVIDER="mobitech")
    @patch("risk.services.send_sms")
    def test_transient_failure_retries_with_same_idempotency_key_without_duplicate_acceptance(self, send_sms):
        send_sms.side_effect = [
            self._failed_result(error_code="timeout", retryable=True),
            self._accepted_result(),
        ]
        alert = self._alert()

        deliver_alert(alert)
        alert.refresh_from_db()
        first_key = str(alert.idempotency_key)
        self.assertEqual(alert.status, Alert.STATUS_RETRY_PENDING)
        self.assertEqual(alert.last_error_classification, "timeout")

        deliver_alert(alert)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_QUEUED)
        self.assertEqual(alert.provider_message_id, "mobitech-message-1")
        self.assertEqual(send_sms.call_count, 2)
        self.assertEqual(send_sms.call_args_list[0].kwargs["idempotency_key"], first_key)
        self.assertEqual(send_sms.call_args_list[1].kwargs["idempotency_key"], first_key)

    @override_settings(SMS_PROVIDER="mobitech")
    @patch("risk.services.send_sms")
    def test_permanent_provider_failure_does_not_retry(self, send_sms):
        send_sms.return_value = self._failed_result(
            error_code="invalid_phone_number",
            retryable=False,
        )
        alert = self._alert()

        deliver_alert(alert)
        alert.refresh_from_db()

        self.assertEqual(alert.status, Alert.STATUS_FAILED)
        self.assertEqual(alert.attempt_count, 1)
        self.assertIsNone(alert.next_retry_at)
        self.assertEqual(alert.last_error_classification, "invalid_phone_number")

    @override_settings(SMS_PROVIDER="stub")
    def test_stub_delivery_is_explicitly_simulated_and_has_no_external_identifier(self):
        alert = self._alert(provider="stub", delivery_kind=Alert.DELIVERY_KIND_SIMULATED)

        deliver_alert(alert)
        alert.refresh_from_db()

        self.assertEqual(alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(alert.delivery_kind, Alert.DELIVERY_KIND_SIMULATED)
        self.assertEqual(alert.provider_acceptance_status, Alert.PROVIDER_ACCEPTANCE_SIMULATED)
        self.assertEqual(alert.provider_delivery_status, Alert.PROVIDER_DELIVERY_SIMULATED)
        self.assertEqual(alert.provider_message_id, "")
        self.assertEqual(alert.external_id, "")

    @patch("risk.tasks.trigger_alerts_for_riskscore")
    @patch("risk.tasks.require_production_alert_eligibility")
    def test_production_truth_gate_runs_before_sms_queuing(self, require_gate, trigger_alerts):
        require_gate.side_effect = ValueError("production_truth_blocked")

        with self.assertRaisesMessage(ValueError, "production_truth_blocked"):
            trigger_alerts_task.run(self.risk_score.id, send_sms=True)

        trigger_alerts.assert_not_called()

    def _alert(self, *, provider="mobitech", delivery_kind=Alert.DELIVERY_KIND_LIVE, **kwargs):
        return Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="+254712345678",
            message="Operational alert body",
            status=kwargs.pop("status", Alert.STATUS_QUEUED),
            delivery_backend=provider,
            delivery_kind=delivery_kind,
            max_attempts=3,
            **kwargs,
        )

    @staticmethod
    def _accepted_result(*, accepted_at=None):
        from risk.providers import DeliveryResult

        return DeliveryResult(
            success=True,
            external_id="mobitech-message-1",
            error="",
            provider="mobitech",
            provider_acceptance_status="accepted",
            provider_accepted_at=accepted_at or timezone.now(),
            request_metadata={"destination_hash": "hash", "message_hash": "hash"},
            response_metadata={"http_status": 200, "response_hash": "hash"},
            external_delivery=True,
        )

    @staticmethod
    def _failed_result(*, error_code, retryable):
        from risk.providers import DeliveryResult

        return DeliveryResult(
            success=False,
            external_id="",
            error="Mobitech request failed.",
            provider="mobitech",
            error_code=error_code,
            retryable=retryable,
            external_delivery=True,
        )
