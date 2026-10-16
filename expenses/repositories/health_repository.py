from django.db import connection


def ping() -> None:
    """Run SELECT 1. Raises django.db.Error if the database cannot be reached."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
