class ServiceUnavailable(Exception):
    """An outside service (such as the OpenAI API) failed. The API returns 503."""


class LimitReached(Exception):
    """A usage limit was reached before any AI call was made. The API returns 429."""
