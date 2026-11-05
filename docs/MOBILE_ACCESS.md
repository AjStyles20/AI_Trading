# Astral AI on a phone: options for remote access

Status: **proposal, not built.** Decisions are the owner's.

## What exists today

The app's layout works on phone-sized screens (0.2.0 and later): below 768px
wide, the sidebar becomes a slide-in drawer opened with ☰, and the chart and
panels use the full width. The desktop layout is unchanged.

That makes Astral usable on a small window or tablet, but **a phone cannot reach
it yet.** The backend listens only on `127.0.0.1` (this PC), behind
`TrustedHostMiddleware`, origin checks and, in the packaged app, a desktop
token. That is deliberate (see `SAFETY_BASELINE.md` and the roadmap's Phase 7):
the backend can place orders, so it must never simply be opened to the network.

## The risk that shapes every option

Anyone who can reach the backend can read your positions and settings, and with
the kill switch disarmed, influence paper (or later live) trading. A phone link
therefore needs, at minimum:

1. **Encryption** in transit (TLS).
2. **Strong authentication** per device, revocable from the desktop.
3. **A separate, narrow gateway**: the phone talks to the gateway, never to the
   backend directly, and the gateway exposes only what the phone needs.
4. **No order placement or disarm from the phone** at first: read-only views,
   alerts and Arm kill switch only. Arming is always safe to allow.

## Options

| Option | How it works | Pros | Cons |
|---|---|---|---|
| A. Private network (e.g. Tailscale or WireGuard) | Phone and PC join a private encrypted network; the phone opens the desktop's gateway over it | No open ports on the internet; strong device keys; free for personal use | Needs an app on both devices; PC must be on |
| B. Same Wi-Fi only | Gateway listens on the home network with a pairing code and TLS | No third-party service | Only works at home; local-network attacks still apply |
| C. Hosted relay | A small cloud service relays between phone and desktop | Works anywhere | A server to run and secure; your data passes through it |
| D. Native app later | React Native app using option A or C | Push notifications, offline | Much more work; app store publishing |

**Recommendation: A, read-only first.** A private network gives encryption and
device identity without exposing anything to the internet. The phone gets the
watchlist, charts, alerts, positions, the session state and Arm kill switch.
Trading actions from the phone come later, behind the same confirmations as
desktop plus device-level authentication, as the roadmap already requires.

## What building option A involves

1. A gateway process on the desktop that binds only to the private-network
   interface, requires a per-device token, and forwards a fixed allowlist of
   read-only endpoints plus Arm.
2. A pairing screen in the desktop app that creates and revokes device tokens
   (stored in the OS credential store) and records each pairing in the audit log.
3. The existing web UI served to the phone through the gateway, with trading
   controls hidden or disabled in phone mode.
4. Tests that the gateway refuses every endpoint not on the allowlist.

This needs the owner to choose the option and install the private-network app.
