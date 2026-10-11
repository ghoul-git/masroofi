class ServiceUnavailable(Exception):
    """An outside service (such as the OpenAI API) failed. The API returns 503."""
