# Nutanix lab credentials

Starting point for `credentials.md`, which is encrypted into `credentials.age`.
Fill in the `<...>` placeholders — everything else is already accurate.

Never commit `credentials.md`; it is gitignored. Only `credentials.age` is
committed, and it is useless without a private key listed in `.age-recipients`.

## FL site (Florida)

| What | Address | User | Secret |
|---|---|---|---|
| Prism Element | `https://10.0.1.243:9440` (VIP) | `admin` | `<prism-fl>` |
| CVM | `10.0.1.242` | `nutanix` | `<cvm-fl>` |
| AHV host | `10.0.1.241` | `root` | `<host-fl>` |
| Ubuntu VM `ntnxlab-ubuntu-fl` | `10.0.1.7` | `markt` | `<vm-fl>` (SSH key also works) |

- Cluster VIP `10.0.1.243`, Data Services IP `10.0.1.244`
- Network `lab` (VLAN 0, no IPAM — guests get IPs from the site router)
- The Ubuntu VM holds an Nvidia GPU in passthrough

## CA site (California)

| What | Address | User | Secret |
|---|---|---|---|
| Prism Element | `https://192.168.86.6:9440` | `admin` | `<prism-ca>` |
| CVM | `192.168.86.6` | `nutanix` | `<cvm-ca>` |
| AHV host | `192.168.86.5` | `root` | `<host-ca>` |
| Ubuntu VM `ntnxlab-ubuntu-ca` | `192.168.86.20` | `markt` | `<vm-ca>` (SSH key also works) |

- Network `vlan.0` (VLAN 0, no IPAM)

## Management API (Nutanix Commander)

| What | Where | User | Secret |
|---|---|---|---|
| Console login | Tailscale `:9443` | `markt` | `<commander>` |

Backed by `deploy/secrets/users.json` (PBKDF2 hashes, gitignored). Reset with:
`python scripts/mgmt_user.py markt admin > deploy/secrets/users.json`

## SSH key

`markt-mac-fleet` (ed25519) — the private half lives on **MT-M4-Pro-mini**.
The public key is registered in Prism *Settings → Cluster Lockdown* on both
clusters, which grants passwordless CVM access and is the reliable way in when
a password is forgotten.

## Access patterns worth remembering

- **AHV host root is only passwordless from its own CVM**: `ssh nutanix@<cvm>`
  then `ssh root@<host>`. From a laptop it always wants the password.
- Host banners identify the box: "Nutanix Controller VM" = CVM,
  "Nutanix AHV" = hypervisor. Hosts have **no `nutanix` user**, only `root`.
- Reset a forgotten Prism password from the CVM:
  `ncli user reset-password user-name=admin password='<new>'`
  (`ncli user unlock` does not exist on AOS 6.8.x; resetting also clears a lockout.)
- Both Ubuntu VMs were built from `noble-cloud-2404` with cloud-init that sets
  `lock_passwd: false` and `ssh_pwauth: true`, so **key and password both work**.
  Verify with `sudo passwd -S markt` → `P` (not `L`).
