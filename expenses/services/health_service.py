import logging

from django.db import Error as DatabaseError

from expenses.repositories import health_repository

logger = logging.getLogger(__name__)


def database_ok() -> bool:
    """True if the database answers. The error is logged, never returned to the caller."""
    try:
        health_repository.ping()
    except DatabaseError:
        logger.exception("Health check: the database is not reachable")
        return False
    return True
