"""Consent under Jordan's Personal Data Protection Law.

A user may use the app only after accepting the current Terms of Service and
Privacy Policy versions (settings.TERMS_VERSION / PRIVACY_VERSION) and
confirming they are 18 or older. Each acceptance is stored as a ConsentRecord.
"""
from django.conf import settings
from django.core.exceptions import ValidationError

from expenses.repositories import consent_repository

# The three boxes on the register and consent pages: form field name -> error when unticked.
REQUIRED_CONSENTS = {
    "accept_terms": "Please agree to the Terms of Service.",
    "accept_privacy": "Please agree to the processing of your data as described in the Privacy Policy.",
    "confirm_age": "Please confirm that you are 18 years or older.",
}


def current_versions() -> tuple[str, str]:
    return settings.TERMS_VERSION, settings.PRIVACY_VERSION


def validate_consents(consents: dict) -> None:
    """consents maps each REQUIRED_CONSENTS key to True when its box was ticked."""
    errors = [message for key, message in REQUIRED_CONSENTS.items() if consents.get(key) is not True]
    if errors:
        raise ValidationError(errors)


def record_consent(user):
    terms_version, privacy_version = current_versions()
    return consent_repository.create(user, terms_version, privacy_version)


def accept(user, consents: dict):
    """Validate the three boxes and record consent to the current versions."""
    validate_consents(consents)
    return record_consent(user)


def has_current_consent(user) -> bool:
    return consent_repository.exists(user, *current_versions())


def latest(user):
    """The user's most recent ConsentRecord, or None."""
    return consent_repository.list_for_user(user).last()
