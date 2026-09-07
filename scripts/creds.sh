#!/usr/bin/env bash
# Encrypted credential store for the Nutanix lab.
#
# Secrets live in credentials.age, which is committed to the repo. It is
# encrypted with age to the SSH public keys listed in .age-recipients, so the
# committed file is useless without a matching private key. The decrypted
# plaintext (credentials.md) is gitignored and only exists while you edit.
#
#   ./scripts/creds.sh show     print the decrypted credentials
#   ./scripts/creds.sh edit     decrypt, open $EDITOR, re-encrypt, shred plaintext
#   ./scripts/creds.sh seal     encrypt an existing credentials.md, then remove it
#   ./scripts/creds.sh init     create credentials.md from the template
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENCRYPTED="$REPO_ROOT/credentials.age"
PLAINTEXT="$REPO_ROOT/credentials.md"
TEMPLATE="$REPO_ROOT/credentials.template.md"
RECIPIENTS="$REPO_ROOT/.age-recipients"
IDENTITY="${AGE_IDENTITY:-$HOME/.ssh/id_ed25519}"

die() { echo "error: $*" >&2; exit 1; }

command -v age >/dev/null 2>&1 || die "age is not installed. Install it with: brew install age"

require_recipients() {
    [ -f "$RECIPIENTS" ] || die "missing $RECIPIENTS — add at least one public key"
    grep -qE '^\s*(ssh-|age1)' "$RECIPIENTS" \
        || die "$RECIPIENTS contains no ssh-* or age1... public keys"
}

require_identity() {
    [ -f "$IDENTITY" ] || die "no SSH private key at $IDENTITY (override with AGE_IDENTITY=/path/to/key)"
}

encrypt() {
    require_recipients
    age --encrypt --recipients-file "$RECIPIENTS" --output "$ENCRYPTED" "$PLAINTEXT"
    echo "encrypted -> $ENCRYPTED"
}

# Remove the plaintext, overwriting first where the platform supports it.
shred_plaintext() {
    [ -f "$PLAINTEXT" ] || return 0
    if rm -P "$PLAINTEXT" 2>/dev/null; then :; else rm -f "$PLAINTEXT"; fi
}

case "${1:-}" in
    show)
        require_identity
        [ -f "$ENCRYPTED" ] || die "no $ENCRYPTED yet — run: $0 init && $0 seal"
        age --decrypt --identity "$IDENTITY" "$ENCRYPTED"
        ;;

    edit)
        require_identity
        require_recipients
        if [ -f "$ENCRYPTED" ]; then
            age --decrypt --identity "$IDENTITY" --output "$PLAINTEXT" "$ENCRYPTED"
        elif [ ! -f "$PLAINTEXT" ]; then
            cp "$TEMPLATE" "$PLAINTEXT"
            echo "no $ENCRYPTED yet — started from the template"
        fi
        chmod 600 "$PLAINTEXT"
        "${EDITOR:-vi}" "$PLAINTEXT"
        encrypt
        shred_plaintext
        echo "plaintext removed. commit $ENCRYPTED to save."
        ;;

    seal)
        [ -f "$PLAINTEXT" ] || die "no $PLAINTEXT to encrypt"
        encrypt
        shred_plaintext
        echo "plaintext removed. commit $ENCRYPTED to save."
        ;;

    init)
        [ -f "$PLAINTEXT" ] && die "$PLAINTEXT already exists — edit it, or run: $0 seal"
        cp "$TEMPLATE" "$PLAINTEXT"
        chmod 600 "$PLAINTEXT"
        echo "created $PLAINTEXT — fill it in, then run: $0 seal"
        ;;

    *)
        sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
