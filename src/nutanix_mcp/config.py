"""Configuration management for the Nutanix MCP server."""

import base64
import json
import sys
from pathlib import Path
from typing import Annotated, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class PECredentialError(Exception):
    """A per-cluster credential is configured but cannot be resolved.

    Deliberately distinct from "no credentials configured": this means the
    operator named a credential for a cluster and it could not be read, which
    must never silently degrade into using a different cluster's password.
    """


class PECredential(BaseModel):
    """Credentials for one Prism Element cluster.

    Takes ``username`` plus exactly one of ``password_file`` or ``password``.
    ``password_file`` is preferred: it keeps the second secret out of the
    process environment and out of whatever config file the MCP client writes,
    matching how the rest of this estate stores CVM and Prism secrets.
    """

    username: str
    password: Optional[SecretStr] = None
    password_file: Optional[str] = None

    def resolve_password(self) -> str:
        """Return the plaintext password, reading ``password_file`` if set.

        Note the caller caches the resulting header on a per-host HTTP client,
        so a rotated secret takes effect when that client is rebuilt — in
        practice, on process restart.
        """
        if self.password is not None:
            return self.password.get_secret_value()
        if not self.password_file:
            raise PECredentialError(
                f"credential for user '{self.username}' sets neither password nor password_file"
            )
        path = Path(self.password_file).expanduser()
        try:
            secret = path.read_text().strip()
        except OSError as e:
            raise PECredentialError(f"cannot read password_file {path}: {e}") from e
        if not secret:
            raise PECredentialError(f"password_file {path} is empty")
        return secret

    def auth_header(self) -> dict[str, str]:
        """Build the Basic auth header for this cluster."""
        token = base64.b64encode(f"{self.username}:{self.resolve_password()}".encode()).decode()
        return {"Authorization": f"Basic {token}"}


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
    pe_username: Optional[str] = Field(
        default=None,
        description=(
            "Optional Prism Element username. Set NUTANIX_PE_USERNAME when the "
            "PE admin credentials differ from Prism Central's. Falls back to "
            "NUTANIX_USERNAME when unset."
        ),
    )
    pe_password: Optional[SecretStr] = Field(
        default=None,
        description=(
            "Optional Prism Element password (SecretStr). Set NUTANIX_PE_PASSWORD "
            "when the PE admin credentials differ from Prism Central's. Falls back "
            "to NUTANIX_PASSWORD when unset."
        ),
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

    # Per-cluster credentials. The global username/password above is a single
    # pair, which is wrong for any estate with more than one PE cluster: each
    # cluster has its own Prism `admin` password, so one credential means every
    # cluster but the first answers 401. NoDecode for the same reason as
    # allowed_pe_hosts — the validator below owns the parsing.
    pe_credentials: Annotated[dict[str, "PECredential"], NoDecode] = Field(
        default_factory=dict,
        description=(
            "Per-cluster Prism Element credentials, keyed by PE host, as a JSON "
            "object. Each value takes 'username' plus either 'password_file' "
            "(preferred) or 'password'. A host listed here is implicitly "
            "allowed and never falls back to the global credential. "
            "Set NUTANIX_PE_CREDENTIALS."
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

    @field_validator("pe_credentials", mode="before")
    @classmethod
    def parse_pe_credentials(cls, v: object) -> dict[str, "PECredential"]:
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"NUTANIX_PE_CREDENTIALS is not valid JSON: {e}") from e
        if not isinstance(v, dict):
            raise ValueError("NUTANIX_PE_CREDENTIALS must be a JSON object keyed by PE host")
        out: dict[str, PECredential] = {}
        for pe_host, entry in v.items():
            cred = entry if isinstance(entry, PECredential) else PECredential.model_validate(entry)
            if cred.password is not None and cred.password_file:
                raise ValueError(
                    f"NUTANIX_PE_CREDENTIALS['{pe_host}'] sets both password and password_file; use one"
                )
            if cred.password is None and not cred.password_file:
                raise ValueError(
                    f"NUTANIX_PE_CREDENTIALS['{pe_host}'] needs either password or password_file"
                )
            out[str(pe_host)] = cred
        return out

    @property
    def base_url(self) -> str:
        """Base URL for Prism Central API requests."""
        return f"https://{self.host}:{self.port}/api"

    @property
    def has_credentials(self) -> bool:
        """Check if valid credentials are configured."""
        return bool(self.username and self.password)

    def get_auth_header(self) -> dict[str, str]:
        """Build the authorization header for Prism Central."""
        if self.username and self.password:
            secret = self.password.get_secret_value()
            credentials = base64.b64encode(f"{self.username}:{secret}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        raise ValueError("No credentials configured. Set NUTANIX_USERNAME and NUTANIX_PASSWORD.")

    def get_pe_auth_header(self) -> dict[str, str]:
        """Build the authorization header for Prism Element.

        Uses NUTANIX_PE_USERNAME / NUTANIX_PE_PASSWORD when set (PE admin
        credentials often differ from Prism Central's), otherwise falls back to
        the Prism Central credentials.

        This is the cluster-agnostic pair. When several PE clusters each have
        their own password, use get_auth_header_for_pe() instead.
        """
        pe_user = self.pe_username or self.username
        pe_secret = self.pe_password or self.password
        if pe_user and pe_secret:
            secret = pe_secret.get_secret_value()
            credentials = base64.b64encode(f"{pe_user}:{secret}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        raise ValueError(
            "No PE credentials configured. Set NUTANIX_PE_USERNAME/NUTANIX_PE_PASSWORD "
            "or NUTANIX_USERNAME/NUTANIX_PASSWORD."
        )

    def get_auth_header_for_pe(self, pe_host: str) -> dict[str, str]:
        """Build the authorization header for one named Prism Element cluster.

        Three tiers, most specific first:

        1. ``pe_credentials[pe_host]`` — this cluster's own credential.
        2. ``NUTANIX_PE_USERNAME``/``PASSWORD`` — one pair for every PE cluster,
           for the common case where PE differs from Prism Central but the PE
           clusters agree with each other.
        3. The Prism Central credential.

        Tier 1 NEVER degrades to tier 2 or 3. That is the whole point: falling
        back would send a different cluster's password, and Prism locks the
        `admin` account for about fifteen minutes after a few failed attempts.
        Where two clusters' passwords resemble each other, a silent fallback
        does not read as a wrong password — it reads as a broken cluster. So a
        missing or unreadable password file has to fail loudly instead.
        """
        cred = self.pe_credentials.get(pe_host)
        if cred is not None:
            return cred.auth_header()
        return self.get_pe_auth_header()

    def is_pe_host_allowed(self, pe_host: str) -> bool:
        """Check if a PE host is in the allowlist.

        Returns True if:
        - The host has its own entry in pe_credentials (configuring a
          credential for a named cluster is itself an authorization of it;
          requiring the host in two places would be a footgun with no security
          value, since both are operator-set config)
        - The allowlist is empty (permissive mode — relies on network controls)
        - The host matches an entry in the allowlist
        """
        if pe_host in self.pe_credentials:
            return True
        if not self.allowed_pe_hosts:
            return True
        return pe_host in self.allowed_pe_hosts

    @property
    def selectable_pe_hosts(self) -> list[str]:
        """Every PE host an operator explicitly named, for a UI to offer.

        The allowlist first, in its own order (its first entry is the UI's
        default), then any host that is configured only through pe_credentials.
        is_pe_host_allowed() accepts those too, so a picker built from the
        allowlist alone would hide clusters the API serves.
        """
        hosts = list(self.allowed_pe_hosts)
        hosts += [h for h in self.pe_credentials if h not in hosts]
        return hosts


def get_settings() -> Settings:
    """Load and validate settings."""
    try:
        return Settings()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
