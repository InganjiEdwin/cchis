from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StrongPasswordValidator:
    """Require a balanced password character mix."""

    def validate(self, password, user=None):
        errors = []

        if not any(character.islower() for character in password):
            errors.append(_("Password must include at least one lowercase letter."))

        if not any(character.isupper() for character in password):
            errors.append(_("Password must include at least one uppercase letter."))

        if not any(character.isdigit() for character in password):
            errors.append(_("Password must include at least one number."))

        if not any(not character.isalnum() for character in password):
            errors.append(_("Password must include at least one symbol."))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _("Your password must include uppercase and lowercase letters, a number, and a symbol.")
