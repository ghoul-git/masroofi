"""The database settings, from DATABASE_URL or the DB_* variables."""
import dj_database_url


def database_from_env(env) -> dict:
    """Django's DATABASES["default"] from environment variables.

    DATABASE_URL (postgres://user:password@host:port/name, as most hosting providers
    give it) takes priority. Options in its query string, such as ?sslmode=require,
    are passed to the driver. Without it, the DB_NAME, DB_USER, DB_PASSWORD, DB_HOST
    and DB_PORT variables are used.
    """
    url = (env.get("DATABASE_URL") or "").strip()
    if url:
        return dj_database_url.parse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env["DB_NAME"],
        "USER": env["DB_USER"],
        "PASSWORD": env["DB_PASSWORD"],
        "HOST": env.get("DB_HOST") or "localhost",
        "PORT": env.get("DB_PORT") or "5432",
    }
