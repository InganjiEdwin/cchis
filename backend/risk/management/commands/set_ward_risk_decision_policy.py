import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.decision_policy import (
    current_ward_risk_decision_policy,
    set_ward_risk_decision_policy,
    validate_ward_risk_decision_policy,
)


class Command(BaseCommand):
    help = "Inspect or update the versioned Phase 5 ward-risk decision threshold policy."

    def add_arguments(self, parser):
        parser.add_argument("--policy-version", default="")
        parser.add_argument("--reason", default="")
        parser.add_argument("--medium-min-probability", type=float, default=None)
        parser.add_argument("--high-min-probability", type=float, default=None)
        parser.add_argument("--watchlist-min-probability", type=float, default=None)
        parser.add_argument("--alert-candidate-min-probability", type=float, default=None)
        parser.add_argument("--urgent-alert-min-probability", type=float, default=None)
        parser.add_argument("--watchlist-min-expected-cases", type=int, default=None)
        parser.add_argument("--alert-candidate-min-expected-cases", type=int, default=None)
        parser.add_argument("--urgent-alert-min-expected-cases", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def _policy_updates(self, options: dict) -> dict:
        updates: dict = {"thresholds": {"risk_level": {}, "alerting": {}}}
        if options["policy_version"]:
            updates["policy_version"] = options["policy_version"]
        if options["medium_min_probability"] is not None:
            updates["thresholds"]["risk_level"]["medium_min_probability"] = options["medium_min_probability"]
        if options["high_min_probability"] is not None:
            updates["thresholds"]["risk_level"]["high_min_probability"] = options["high_min_probability"]
        if options["watchlist_min_probability"] is not None:
            updates["thresholds"]["alerting"]["watchlist_only_min_probability"] = options[
                "watchlist_min_probability"
            ]
        if options["alert_candidate_min_probability"] is not None:
            updates["thresholds"]["alerting"]["alert_candidate_min_probability"] = options[
                "alert_candidate_min_probability"
            ]
        if options["urgent_alert_min_probability"] is not None:
            updates["thresholds"]["alerting"]["urgent_alert_min_probability"] = options[
                "urgent_alert_min_probability"
            ]
        if options["watchlist_min_expected_cases"] is not None:
            updates["thresholds"]["alerting"]["watchlist_min_expected_cases"] = options[
                "watchlist_min_expected_cases"
            ]
        if options["alert_candidate_min_expected_cases"] is not None:
            updates["thresholds"]["alerting"]["alert_candidate_min_expected_cases"] = options[
                "alert_candidate_min_expected_cases"
            ]
        if options["urgent_alert_min_expected_cases"] is not None:
            updates["thresholds"]["alerting"]["urgent_alert_min_expected_cases"] = options[
                "urgent_alert_min_expected_cases"
            ]
        updates["thresholds"] = {key: value for key, value in updates["thresholds"].items() if value}
        return {key: value for key, value in updates.items() if value}

    def handle(self, *args, **options):
        updates = self._policy_updates(options)
        if not updates:
            self.stdout.write(json.dumps(current_ward_risk_decision_policy(), indent=2, sort_keys=True, default=str))
            return

        try:
            if options["dry_run"]:
                policy = current_ward_risk_decision_policy()
                from risk.ml.decision_policy import _deep_merge  # local import keeps command output focused

                candidate = _deep_merge(policy, updates)
                validate_ward_risk_decision_policy(candidate)
                self.stdout.write(json.dumps(candidate, indent=2, sort_keys=True, default=str))
                return

            result = set_ward_risk_decision_policy(
                policy_updates=updates,
                reason=options["reason"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
