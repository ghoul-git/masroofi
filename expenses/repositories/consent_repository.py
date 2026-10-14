from expenses.models import ConsentRecord


def create(user, terms_version, privacy_version) -> ConsentRecord:
    return ConsentRecord.objects.create(user=user, terms_version=terms_version, privacy_version=privacy_version)


def exists(user, terms_version, privacy_version) -> bool:
    return ConsentRecord.objects.filter(
        user=user, terms_version=terms_version, privacy_version=privacy_version
    ).exists()


def list_for_user(user):
    return ConsentRecord.objects.filter(user=user).order_by("accepted_at", "id")
