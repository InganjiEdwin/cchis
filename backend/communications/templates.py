from dataclasses import dataclass


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    text_body: str
    html_body: str


def build_password_reset_email(reset_token: str, reset_link: str) -> EmailTemplate:
    return EmailTemplate(
        subject="CHIS password reset request",
        text_body=(
            "A request was received to reset your CHIS password.\n\n"
            f"Open this reset link: {reset_link}\n\n"
            f"If needed, you can also use this reset token: {reset_token}\n\n"
            "If you did not request a password reset, you can ignore this message."
        ),
        html_body=(
            "<p>A request was received to reset your CHIS password.</p>"
            f"<p><a href=\"{reset_link}\">Create a new password</a></p>"
            f"<p><strong>Reset token:</strong> {reset_token}</p>"
            "<p>If you did not request a password reset, you can ignore this message.</p>"
        ),
    )


def build_access_request_acknowledgement_email(
    *,
    full_name: str,
    organization: str,
    desired_role: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject="CCHIS access request received",
        text_body=(
            f"Hello {full_name},\n\n"
            "Your request for CCHIS dashboard access has been received.\n"
            f"Requested role: {desired_role}\n"
            f"Organization: {organization}\n\n"
            "We will review your request and follow up through official channels."
        ),
        html_body=(
            f"<p>Hello {full_name},</p>"
            "<p>Your request for CCHIS dashboard access has been received.</p>"
            f"<p><strong>Requested role:</strong> {desired_role}<br/>"
            f"<strong>Organization:</strong> {organization}</p>"
            "<p>We will review your request and follow up through official channels.</p>"
        ),
    )


def build_access_request_decision_email(
    *,
    full_name: str,
    approved: bool,
    decision_message: str = "",
) -> EmailTemplate:
    outcome_text = (
        "Your request has been approved. Our team will share onboarding or activation guidance shortly."
        if approved
        else "Your request is not approved at this time."
    )
    decision_label = "approved" if approved else "not approved"
    note_text = f"\n\nAdditional note:\n{decision_message}" if decision_message else ""
    note_html = f"<p><strong>Additional note:</strong> {decision_message}</p>" if decision_message else ""

    return EmailTemplate(
        subject=f"CCHIS access request {decision_label}",
        text_body=f"Hello {full_name},\n\n{outcome_text}{note_text}",
        html_body=f"<p>Hello {full_name},</p><p>{outcome_text}</p>{note_html}",
    )
