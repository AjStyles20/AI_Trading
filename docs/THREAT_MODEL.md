# Astral AI threat model

A map of what Astral protects, from whom, what defends it today, and what does
not yet. It complements `SAFETY_BASELINE.md` (trading invariants) and is meant
to be updated whenever a new way into the app is added (see `MOBILE_ACCESS.md`).

Last reviewed: 2026-11-05, version 0.3.0.

## What is worth protecting

| Asset | Where it lives | Why it matters |
|---|---|---|
| Ability to place orders | Backend order path (`submit_guarded_order`) | Real money once live trading is enabled |
| Broker and AI API keys | OS credential store | Account takeover, spending, data access |
| Kill switch and risk limits | SQLite settings | Removing them allows unchecked orders |
| Positions, trades, journal, chat history | SQLite (`astral.db`), backups folder | Private financial and personal data |
| AI long-term memory | ChromaDB folder next to the database | Private conversation content |

## Who might attack, and how

| Actor | Realistic route in |
|---|---|
| A malicious website open in your browser | Requests to `127.0.0.1:8000`, DNS rebinding |
| Content the AI reads (headlines, pasted text, images) | Prompt injection steering the AI's reply |
| Another program or user on this PC | Reading the data folder, calling the local API |
| Anyone with your GitHub access, or the public | The public repository and its releases |
| Someone on your Tailscale network | Calls to the phone gateway without a paired token |
| A compromised dependency | Code running inside the backend or desktop app |

## Defences in place

**Local API**
- Listens on `127.0.0.1` only; never on the network.
- `TrustedHostMiddleware` allows only `127.0.0.1` and `localhost` hosts, which
  blocks DNS rebinding.
- Requests from origins other than the app's own are rejected, and browser
  requests marked cross-site without an origin are refused (fetch metadata).
- No wildcard CORS with credentials.
- The packaged desktop app runs the backend with a random per-session token that
  every `/api/` call must carry.

**Orders and risk** (details in `SAFETY_BASELINE.md`)
- One guarded submission path with kill switch re-read, risk checks before and
  after broker normalization, and persisted intents before execution.
- Kill switch armed by default. Disarming needs `DISARM` typed, is limited to
  paper trading, and is audit-logged. Live trading can't be enabled while disarmed.
- Non-finite numbers are rejected throughout the order path.

**AI**
- The AI cannot place, change or cancel orders, or change settings.
- Its replies are rendered as Markdown without raw HTML, so they cannot inject
  markup or scripts.
- Suggestion cards accept only three safe kinds (open chart, add to watchlist,
  price alert), validated like user input, and act only after the user approves.
- Chart context sent to the provider is validated and bounded; real account data
  is never sent.

**Secrets and data**
- API keys are in the OS credential store, not SQLite; the audit log and backups
  never contain key values.
- Backups stay on this computer; the repository is public, so data never goes there.
- Settings changes are recorded in an audit log.

**Phone gateway** (optional, off by default)
- A separate process; the backend itself stays loopback-only.
- Listens only on a Tailscale address (100.64.0.0/10) or this computer; refuses
  0.0.0.0, home-network addresses and hostnames.
- Each phone has its own token, stored only as a hash and revocable; pairing and
  revoking are audit-logged. The pairing link carries the token in the URL
  fragment, which browsers never send to a server.
- Forwards only an allowlist of read-only requests plus arming the kill switch.
  Orders, disarming, settings changes, starting sessions and AI calls are refused.
- Never forwards the phone's cookies, origin or fetch metadata to the backend.

**Desktop shell**
- Renderer sandboxed, with context isolation and no Node integration.
- New windows are denied and navigation is limited to the app's own origin.
- Dependencies are locked with hashes (backend) and `npm audit` is clean.

## Known gaps

| Gap | Risk | Suggested next step |
|---|---|---|
| No content security policy for the desktop renderer | A script injection bug would face no second barrier | Add a strict policy, reviewed as its own change |
| Electron grants page permissions by default | A compromised page could request camera, microphone or location | Allow only notifications and clipboard writing |
| Data folder is not encrypted at rest | Anyone with access to your user account can read trades and chats | Rely on disk encryption (BitLocker) or add app-level encryption |
| Dev server runs without the desktop token | During development, any local program can call the API | Acceptable for development; never expose the dev server |
| Legacy Python strategies run in-process | Not an OS sandbox | Prefer declarative strategies; never run third-party Python |
| Unsigned installer | Users can't verify the installer's origin | Code-signing certificate before sharing with others |
| Phone gateway works only with the backend run from source | Packaged users can't use it yet | Have the desktop app start it with its session token |
| Phone gateway speaks HTTP inside Tailscale | Relies on Tailscale's WireGuard encryption | Keep it bound to the Tailscale address only (enforced) |

## When to update this document

Update it with any change that adds an entry point (network listener, IPC
channel, file import, new AI capability), stores a new kind of sensitive data,
or changes how orders, the kill switch or credentials are handled.
