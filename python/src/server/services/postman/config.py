"""Configuration for Postman API client. Modified for programmatic initialization."""


class PostmanConfig:
    """Postman API configuration. Accepts values directly rather than reading from environment."""

    def __init__(
        self,
        api_key: str = "",
        workspace_id: str = "",
        rate_limit_delay: int = 60,
        max_retries: int = 3,
        timeout: int = 30,
        use_proxy: bool = False,
    ):
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.log_level = "INFO"

        if not use_proxy:
            self.proxies = {"http": None, "https": None}
        else:
            self.proxies = None

    def validate(self):
        """Validate that required configuration is present."""
        if not self.api_key:
            raise ValueError("POSTMAN_API_KEY not configured. Set it in Cortex Settings.")
        if not self.api_key.startswith("PMAK-"):
            raise ValueError("Invalid POSTMAN_API_KEY format. Keys should start with 'PMAK-'.")

    @property
    def base_url(self):
        return "https://api.getpostman.com"

    @property
    def headers(self):
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}
