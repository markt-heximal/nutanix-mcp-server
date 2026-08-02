"""Configuration management for the Nutanix MCP server."""

import base64
import sys
from typing import Annotated, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables.

    All settings are prefixed with NUTANIX_ in environment variables.
    Example: NUTANIX_HOST, NUTANIX_USERNAME, etc.
    """

    model_config = SettingsConfigDict(
        env_prefix="NUTANIX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        description="Prism Central hostname or IP (required — set NUTANIX_HOST)",
    )
    port: int = Field(default=9440, description="Prism Central API port")
    username: Optional[str] = Field(default=None, description="Username for basic auth")
    password: Optional[SecretStr] = Field(
        default=None,
        description="Password for basic auth (SecretStr — masked in repr/logs)",
    )
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    pe_only: bool = Field(
        default=False,
        description=(
            "PE-only mode. When true, only Prism Element (pe_*) tools are "
            "exposed and Prism Central tools are hidden and blocked. Use this "
            "when no Prism Central is deployed so the model never attempts "
            "central-plane calls that would fail. Set NUTANIX_PE_ONLY=true."
        ),
    )
    log_level: str = Field(
        default="INFO",
        description="Log level for stderr diagnostics (DEBUG, INFO, WARNING, ERROR)",
    )

    # Security: restrict which PE hosts can be targeted.
    # NoDecode prevents pydantic-settings from JSON-decoding the env value, so
    # the mode="before" validator below can accept a comma-separated string
    # (e.g. NUTANIX_ALLOWED_PE_HOSTS=10.0.1.242,10.0.2.242). A JSON array
    # (["10.0.1.242"]) still works too.
    allowed_pe_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Allowlist of Prism Element hosts (IPs or hostnames). "
            "If empty, PE tools will only accept hosts discovered via list_hosts. "
            "Set NUTANIX_ALLOWED_PE_HOSTS as comma-separated values."
        ),
    )

    @field_validator("host", mode="before")
    @classmethod
    def validate_host(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("NUTANIX_HOST is required. Set it as an environment variable or in a .env file.")
        return v

    @field_validator("allowed_pe_hosts", mode="before")
    @classmethod
    def parse_pe_hosts(cls, v):
        if isinstance(v, str):
            s = v.strip()
            # Accept a JSON array (["a","b"]) or a comma-separated string (a,b).
            # NoDecode on the field means we receive the raw string either way.
            if s.startswith("["):
                import json

                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(h).strip() for h in parsed if str(h).strip()]
                except json.JSONDecodeError:
                    pass
            return [h.strip() for h in s.split(",") if h.strip()]
        return v or []

    @property
    def base_url(self) -> str:
        """Base URL for Prism Central API requests."""
        return f"https://{self.host}:{self.port}/api"

    @property
    def has_credentials(self) -> bool:
        """Check if valid credentials are configured."""
        return bool(self.username and self.password)

    def get_auth_header(self) -> dict[str, str]:
        """Build the authorization header."""
        if self.username and self.password:
            secret = self.password.get_secret_value()
            credentials = base64.b64encode(f"{self.username}:{secret}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        raise ValueError("No credentials configured. Set NUTANIX_USERNAME and NUTANIX_PASSWORD.")

    def is_pe_host_allowed(self, pe_host: str) -> bool:
        """Check if a PE host is in the allowlist.

        Returns True if:
        - The allowlist is empty (permissive mode — relies on network controls)
        - The host matches an entry in the allowlist
        """
        if not self.allowed_pe_hosts:
            return True
        return pe_host in self.allowed_pe_hosts


def get_settings() -> Settings:
    """Load and validate settings."""
    try:
        return Settings()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
