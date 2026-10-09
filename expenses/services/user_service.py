from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


def register_user(username, email, password):
    if not username:
        raise ValidationError("Username is required.")
    if User.objects.filter(username=username).exists():
        raise ValidationError("Username is already taken.")
    validate_password(password)
    return User.objects.create_user(username=username, email=email, password=password)
