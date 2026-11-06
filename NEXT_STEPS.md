# Next steps for the owner

Everything below needs your accounts, your keys, your devices or your decision,
so it was left for you. The app works without any of it: charts, backtests,
strategies and paper trading run as they are.

Do them in this order. Each step says how to check that it worked.

## 1. Choose an AI provider (optional, 5 minutes)

The AI chat, summaries and suggestion cards need one provider. Without one they
say "unavailable", and the visual strategy builder still works.

1. Read `docs/AI_GUIDE.md` → "Which one should I pick?". On this PC
   (about 4 GB of memory) **Groq** is the practical choice: free, and it puts no
   load on the computer. Ollama needs far more memory.
2. Create a Groq account at console.groq.com and create an API key.
3. In Astral: **Settings → AI Provider → Groq**, paste the key, save.
   The key goes into the Windows credential store, not the database.
4. **Check:** ask the chat "What is my kill switch state?". It should answer
   from your real settings.

Never paste a key into the chat, a GitHub issue or the diagnostics report. The
report lists stored credentials by name only.

## 2. Turn on disk encryption (10 minutes, once)

Astral's data folder (trades, chats, journal) is not encrypted by the app. On
Windows 10 Home, use **Settings → Update & Security → Device encryption** if it is
listed. BitLocker itself needs Windows Pro. Save the recovery key somewhere other
than this PC.

**Check:** the setting shows "On".

## 3. Phone access over Tailscale (optional, 15 minutes)

1. Install Tailscale on this PC and on the phone. Sign in to the **same** account
   on both. On the PC, note its Tailscale address (starts with `100.`).
2. In Astral: **Settings → Phone access**, enter that address, click **Turn on**,
   then quit and reopen Astral.
3. Enter a phone name, click **Pair a phone**, and open the link on the phone. It
   is shown once.
4. **Check:** the phone shows charts and the header "Phone · read-only". Trading,
   Disarm and Settings are not there; **Arm** is.
5. Lost phone: **Revoke** it in Settings. To stop phone access completely,
   **Turn off** and restart Astral.

From source instead of the installed app: run `python backend/main.py`, then
`python backend/phone_gateway.py --host 100.x.y.z` in a second terminal.

If the phone cannot connect, look at `logs/phone-gateway.log` in the data folder
(Settings → Diagnostics report shows where the data folder is).

## 4. Broker sandbox keys (optional, when you want to go past paper)

Paper trading needs no keys. To test against a real broker's **test** system:

1. Create a sandbox or testnet account: Alpaca paper, Binance testnet or Bitget
   demo. Use test keys only.
2. In Settings, open that broker's section (Binance, Bitget Broker or Alpaca
   Broker), choose its testnet/sandbox option, and paste the test keys.
3. Follow `docs/V5_SANDBOX_READINESS.md` from start to end, and keep its
   checklist results.

The kill switch stays **armed** until you disarm it yourself by typing DISARM.
While armed, Astral only watches and reconciles; it places no orders.

## 5. Real money: not yet

Autonomous trading with real money is deliberately gated (README → "Maturity
gates"). Before it is even considered, you need: a completed sandbox checklist,
a long paper and sandbox soak with no unresolved incidents, hard capital limits
in Settings, and a separate review of the change that enables it. Nothing in the
app does this for you, and it should not.

## 6. Before sharing the installer with anyone else

- **Code signing:** the installer is unsigned, so Windows SmartScreen warns about
  it. A code-signing certificate (from a certificate authority, paid yearly) fixes
  that. The build is set up in `frontend/package.json` → `build`; signing needs the
  certificate and its password as CI secrets, which only you can add.
- **Electron page permissions and content security policy:** listed as open in
  `docs/THREAT_MODEL.md`. Tightening them is a separate change that should be
  reviewed on its own, because a mistake there can break the app's own pages.

## 7. Asking for help

**Settings → Diagnostics report → Create report**, read it, then **Copy report**
and paste it with your question. It contains version, safety settings, record
counts and recent activity, never key values, and replaces your home folder
with `~`.

## Where things are kept

- **Versions:** `CHANGELOG.md`, and git tags `v0.2.0` onward with GitHub releases.
- **Backups:** Settings → Backups. They stay on this PC, in the data folder's
  `backups/`. The GitHub repository is **public**, so never commit the database
  or a backup. Copy backups to a USB drive or private cloud folder yourself.
- **Guides:** `docs/USER_GUIDE.md`, `docs/AI_GUIDE.md`, `docs/MOBILE_ACCESS.md`,
  `docs/SAFETY_BASELINE.md`, `docs/THREAT_MODEL.md`.
