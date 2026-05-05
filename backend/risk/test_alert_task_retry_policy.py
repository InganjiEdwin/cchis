from django.test import SimpleTestCase

from risk.tasks import trigger_alerts_task


class AlertTaskRetryPolicyTests(SimpleTestCase):
    def test_trigger_alerts_task_does_not_autoretry_business_rule_value_errors(self):
        self.assertIn(Exception, trigger_alerts_task.autoretry_for)
        self.assertIn(ValueError, trigger_alerts_task.dont_autoretry_for)

