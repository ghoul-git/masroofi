from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

User = get_user_model()

USERNAME_TAKEN = "Username is already taken."


def register_user(username, email, password):
    if not username:
        raise ValidationError("Username is required.")
    if email:
        validate_email(email)  # raises "Enter a valid email address."
    if User.objects.filter(username=username).exists():
        raise ValidationError(USERNAME_TAKEN)
    validate_password(password)
    try:
        # Two sign-ups with the same name can both pass the check above;
        # the database unique constraint catches the second one.
        with transaction.atomic():
            return User.objects.create_user(username=username, email=email, password=password)
    except IntegrityError:
        raise ValidationError(USERNAME_TAKEN)
