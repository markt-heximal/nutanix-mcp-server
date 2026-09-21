"""Tests for per-cluster Prism Element credentials.

The behaviour under test exists because one global username/password is wrong
for any estate with more than one PE cluster: each cluster carries its own
Prism `admin` password, so a single credential means every cluster but the
first answers 401.

The no-fallback rule is the load-bearing part. Prism locks `admin` for about
fifteen minutes after a few failed attempts, and where two sites' passwords are
similar a silent fallback does not read as a wrong password — it reads as a
broken cluster. So a configured-but-unreadable credential must raise, never
quietly try the global one.
"""

import base64
import json
import os

import pytest
from pydantic import ValidationError as PydanticValidationError

from nutanix_mcp.config import PECredential, PECredentialError, Settings

FL = "10.0.1.242"
CA = "192.168.86.6"

BASE = {
    "host": FL,
    "username": "admin",
    "password": "fl-secret",
}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep these tests off the operator's real configuration.

    Settings reads a .env from the current directory and NUTANIX_* from the
    environment, so without this the suite's results depend on whichever
    cluster the machine happens to be pointed at.
    """
    for key in [k for k in os.environ if k.startswith("NUTANIX_")]:
        monkeypatch.delenv(key, raising=False)


def _settings(**overrides) -> Settings:
    # _env_file=None completes the isolation started by the fixture above.
    return Settings(_env_file=None, **{**BASE, **overrides})


def _decode(header: dict[str, str]) -> tuple[str, str]:
    """Pull (username, password) back out of a Basic auth header."""
    raw = header["Authorization"].removeprefix("Basic ")
    user, _, password = base64.b64decode(raw).decode().partition(":")
    return user, password


# ─── parsing ──────────────────────────────────────────────────────────────


def test_absent_credentials_default_to_empty():
    assert _settings().pe_credentials == {}


def test_parses_json_object_from_env_string():
    s = _settings(
        pe_credentials=json.dumps(
            {CA: {"username": "admin", "password": "ca-secret"}}
        )
    )
    assert set(s.pe_credentials) == {CA}
    assert s.pe_credentials[CA].username == "admin"


def test_rejects_malformed_json():
    with pytest.raises(PydanticValidationError, match="not valid JSON"):
        _settings(pe_credentials="{not json")


def test_rejects_non_object_json():
    with pytest.raises(PydanticValidationError, match="JSON object"):
        _settings(pe_credentials='["10.0.1.242"]')


def test_rejects_entry_with_both_password_and_file():
    payload = json.dumps(
        {CA: {"username": "admin", "password": "x", "password_file": "/tmp/x"}}
    )
    with pytest.raises(PydanticValidationError, match="use one"):
        _settings(pe_credentials=payload)


def test_rejects_entry_with_neither_password_nor_file():
    with pytest.raises(PydanticValidationError, match="either password or password_file"):
        _settings(pe_credentials=json.dumps({CA: {"username": "admin"}}))


# ─── resolution ───────────────────────────────────────────────────────────


def test_host_without_entry_uses_global_credential():
    s = _settings(pe_credentials=json.dumps({CA: {"username": "admin", "password": "ca-secret"}}))
    assert _decode(s.get_auth_header_for_pe(FL)) == ("admin", "fl-secret")


def test_host_without_entry_prefers_the_pe_pair_over_prism_central():
    """Tier 2: NUTANIX_PE_USERNAME/PASSWORD, for PE clusters that agree with each other."""
    s = _settings(
        pe_username="pe-admin",
        pe_password="pe-secret",
        pe_credentials=json.dumps({CA: {"username": "admin", "password": "ca-secret"}}),
    )
    assert _decode(s.get_auth_header_for_pe(FL)) == ("pe-admin", "pe-secret")


def test_named_host_wins_over_the_pe_pair():
    """Tier 1 beats tier 2 — the whole reason per-host credentials exist."""
    s = _settings(
        pe_username="pe-admin",
        pe_password="pe-secret",
        pe_credentials=json.dumps({CA: {"username": "ca-admin", "password": "ca-secret"}}),
    )
    assert _decode(s.get_auth_header_for_pe(CA)) == ("ca-admin", "ca-secret")


def test_host_with_entry_uses_its_own_credential():
    s = _settings(pe_credentials=json.dumps({CA: {"username": "ca-admin", "password": "ca-secret"}}))
    assert _decode(s.get_auth_header_for_pe(CA)) == ("ca-admin", "ca-secret")


def test_password_file_is_read_from_disk(tmp_path):
    secret = tmp_path / "prism-admin-ca"
    secret.write_text("ca-from-file\n")
    s = _settings(
        pe_credentials=json.dumps({CA: {"username": "admin", "password_file": str(secret)}})
    )
    assert _decode(s.get_auth_header_for_pe(CA)) == ("admin", "ca-from-file")


def test_password_file_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    secret = tmp_path / "ca-pass"
    secret.write_text("tilde-secret")
    s = _settings(pe_credentials=json.dumps({CA: {"username": "admin", "password_file": "~/ca-pass"}}))
    assert _decode(s.get_auth_header_for_pe(CA)) == ("admin", "tilde-secret")


# ─── the no-fallback rule ─────────────────────────────────────────────────


def test_missing_password_file_raises_and_does_not_fall_back(tmp_path):
    """The whole point: never send one cluster's password to another.

    Both lower tiers are populated here, so a fallback of either kind would
    succeed silently and spend a lockout attempt on the wrong credential.
    """
    s = _settings(
        pe_username="pe-admin",
        pe_password="pe-secret",
        pe_credentials=json.dumps(
            {CA: {"username": "admin", "password_file": str(tmp_path / "absent")}}
        ),
    )
    with pytest.raises(PECredentialError, match="cannot read password_file"):
        s.get_auth_header_for_pe(CA)


def test_empty_password_file_raises_and_does_not_fall_back(tmp_path):
    secret = tmp_path / "empty"
    secret.write_text("   \n")
    s = _settings(
        pe_credentials=json.dumps({CA: {"username": "admin", "password_file": str(secret)}})
    )
    with pytest.raises(PECredentialError, match="is empty"):
        s.get_auth_header_for_pe(CA)


def test_credential_without_password_source_raises():
    """Constructed directly, bypassing the settings validator."""
    with pytest.raises(PECredentialError, match="neither password nor password_file"):
        PECredential(username="admin").resolve_password()


# ─── allowlist interaction ────────────────────────────────────────────────


def test_configured_host_is_implicitly_allowed():
    s = _settings(
        allowed_pe_hosts=FL,
        pe_credentials=json.dumps({CA: {"username": "admin", "password": "ca-secret"}}),
    )
    assert s.is_pe_host_allowed(CA)
    assert s.is_pe_host_allowed(FL)


def test_unconfigured_host_still_blocked_by_allowlist():
    s = _settings(
        allowed_pe_hosts=FL,
        pe_credentials=json.dumps({CA: {"username": "admin", "password": "ca-secret"}}),
    )
    assert not s.is_pe_host_allowed("10.9.9.9")


def test_empty_allowlist_remains_permissive():
    assert _settings().is_pe_host_allowed("10.9.9.9")


# ─── hosts offered to the UI ──────────────────────────────────────────────


def _cred(password: str) -> dict[str, str]:
    return {"username": "admin", "password": password}


def test_selectable_hosts_include_credential_only_hosts():
    s = _settings(allowed_pe_hosts=FL, pe_credentials=json.dumps({CA: _cred("ca-secret")}))
    assert s.selectable_pe_hosts == [FL, CA]


def test_selectable_hosts_keep_allowlist_first_and_do_not_duplicate():
    s = _settings(
        allowed_pe_hosts=f"{FL},{CA}",
        pe_credentials=json.dumps({CA: _cred("ca-secret"), "10.0.2.242": _cred("x")}),
    )
    assert s.selectable_pe_hosts == [FL, CA, "10.0.2.242"]


def test_selectable_hosts_from_credentials_alone():
    s = _settings(pe_credentials=json.dumps({CA: _cred("ca-secret")}))
    assert s.selectable_pe_hosts == [CA]


def test_selectable_hosts_empty_when_nothing_named():
    assert _settings().selectable_pe_hosts == []
