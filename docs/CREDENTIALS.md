# Encrypted credential store

Lab credentials live in **`credentials.age`**, which *is* committed to this
repo. It's encrypted with [age](https://github.com/FiloSottile/age) to the SSH
public keys in `.age-recipients`, so the committed file is useless without a
matching private key.

This is deliberately different from a gitignored plaintext file: gitignore is
one `git add -f` away from a leak, and this repo is pushed to GitHub. An
encrypted blob is safe even if it's committed, cloned, or backed up.

## Setup (once)

```bash
brew install age
```

Your SSH key is the decryption key — `markt-mac-fleet` is already listed in
`.age-recipients`, so any machine holding that private key can read the store.
No new secret to manage or lose.

## Daily use

```bash
./scripts/creds.sh show     # print credentials to the terminal
./scripts/creds.sh edit     # decrypt → $EDITOR → re-encrypt → shred plaintext
```

`edit` is the normal path: it decrypts to `credentials.md`, opens your editor,
re-encrypts on save, and removes the plaintext. Then commit:

```bash
git add credentials.age && git commit -m "chore: update credentials"
```

## First time populating it

```bash
./scripts/creds.sh init     # copies credentials.template.md → credentials.md
$EDITOR credentials.md      # fill in the <...> placeholders
./scripts/creds.sh seal     # encrypt and remove the plaintext
```

## Adding another machine

Append that machine's SSH **public** key to `.age-recipients` (public keys are
safe to commit), then re-encrypt so the new recipient is included:

```bash
./scripts/creds.sh edit     # save without changes is enough
git add .age-recipients credentials.age
```

Removing a line revokes that key for future versions — but anything already
committed stays readable in git history by whoever held the key, so **rotate
the affected secrets** rather than relying on removal alone.

## Using a different key

```bash
AGE_IDENTITY=~/.ssh/other_key ./scripts/creds.sh show
```

## What's committed vs. not

| File | Committed | Contents |
|---|---|---|
| `credentials.age` | ✅ | encrypted secrets |
| `.age-recipients` | ✅ | public keys only |
| `credentials.template.md` | ✅ | placeholders, no secrets |
| `credentials.md` | ❌ gitignored | decrypted plaintext, transient |

The gitignore rules are verified — `git check-ignore credentials.md` matches,
and `credentials.age` is deliberately *not* ignored so it can be committed.

> **Losing the key means losing the store.** The private half of
> `markt-mac-fleet` is the only way in. Keep a copy somewhere safe (a password
> manager entry, or a second recipient key on another machine).
