#!/usr/bin/env python3
"""Generate a password hash / user record for the Nutanix management API.

The management API reads users from MGMT_USERS_FILE (a JSON file) or the
MGMT_USERS env var, mapping username -> {password_hash, role}. Passwords are
never stored in plaintext; this tool derives a PBKDF2-SHA256 hash the API can
verify.

Usage
-----
    # Print one user record you can paste into users.json:
    python scripts/mgmt_user.py alice admin

    # Read the password from stdin instead of a prompt (for scripting):
    echo 's3cret' | python scripts/mgmt_user.py alice admin --stdin

Roles: viewer (read-only) | operator (non-destructive writes) | admin (all).
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys

ITERATIONS = 200_000
ROLES = ("viewer", "operator", "admin")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${derived.hex()}"


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--stdin"]
    use_stdin = "--stdin" in argv
    if len(args) != 2:
        print(__doc__)
        return 2
    username, role = args
    if role not in ROLES:
        print(f"error: role must be one of {', '.join(ROLES)}", file=sys.stderr)
        return 2

    if use_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass(f"Password for {username}: ")
        if password != getpass.getpass("Confirm password: "):
            print("error: passwords do not match", file=sys.stderr)
            return 1
    if not password:
        print("error: empty password", file=sys.stderr)
        return 1

    record = {username: {"password_hash": hash_password(password), "role": role}}
    print(json.dumps(record, indent=2))
    print(
        "\n# Merge the object above into your users.json (or MGMT_USERS). "
        "Example users.json:\n"
        '# { "alice": { "password_hash": "...", "role": "admin" },\n'
        '#   "bob":   { "password_hash": "...", "role": "viewer" } }',
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
