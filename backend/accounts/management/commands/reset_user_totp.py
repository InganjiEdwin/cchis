from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.two_factor import (
    build_totp_provisioning_uri,
    generate_totp_secret,
    get_two_factor_policy_for_user,
)


User = get_user_model()


class Command(BaseCommand):
    help = "Reset, replace, or disable a user's TOTP configuration for local recovery and testing."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username to update.")
        parser.add_argument(
            "--secret",
            dest="secret",
            default="",
            help="Optional base32 TOTP secret to set explicitly instead of generating a new one.",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Disable TOTP for the user and clear the current secret.",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        provided_secret = options["secret"].strip()
        disable = bool(options["disable"])

        if not username:
            raise CommandError("Username is required.")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f'User "{username}" does not exist.') from exc

        user.pre_auth_tokens.filter(used_at__isnull=True).update(used_at=timezone.now())

        if disable:
            user.totp_secret = ""
            user.is_totp_enabled = False
            user.save(update_fields=["totp_secret", "is_totp_enabled"])
            self.stdout.write(self.style.SUCCESS(f'Disabled TOTP for "{user.username}".'))
            self.stdout.write("Any pending pre-auth sessions were invalidated.")
            return

        secret = provided_secret or generate_totp_secret()
        user.totp_secret = secret
        user.is_totp_enabled = True
        user.save(update_fields=["totp_secret", "is_totp_enabled"])

        provisioning_uri = build_totp_provisioning_uri(
            secret=secret,
            username=user.username,
            issuer="CCHIS",
        )

        self.stdout.write(self.style.SUCCESS(f'Reset TOTP for "{user.username}".'))
        self.stdout.write(f"Role: {user.role}")
        self.stdout.write(f"Policy: {get_two_factor_policy_for_user(user)}")
        self.stdout.write(f"Manual entry key: {secret}")
        self.stdout.write(f"Provisioning URI: {provisioning_uri}")
        self.stdout.write("Replace any stale authenticator entry with the new key or QR provisioning URI.")
