# Astral AI desktop client

From the repository root, install and start the Python backend:

```bash
pip install -r backend/requirements.txt
python backend/main.py
```

In another terminal, start the desktop client:

```bash
cd frontend
npm ci --legacy-peer-deps
npm run electron:dev
```

For a production-renderer smoke test in the source checkout:

```bash
cd frontend
npm run build
npx electron .
```

The built renderer uses the private `astral://app` protocol. Electron serves bundled assets and forwards `/api/` to the backend at `127.0.0.1:8000`. The backend must be started separately and remains bound to loopback. If it is unavailable, API requests return 503.

To build a Windows installer, run `scripts/build_windows_backend.ps1` in PowerShell from the repository root, then run `npm ci --legacy-peer-deps` and `npm run electron:build` in `frontend`. The installer includes the Python backend and stores SQLite and AI memory under the user's application data directory. The packaged desktop starts and stops its own backend on loopback; if port 8000 is occupied, startup fails instead of attaching to an existing service.

The GitHub Windows desktop workflow builds the bundle, tests its authenticated backend endpoints, opens the unpacked Electron application, verifies the renderer and API path, and attaches an unsigned installer to the workflow run for seven days. A Windows installation and broker sandbox exercise on the target machine remain necessary before calling it a release. Existing source-checkout data under `database/` is not migrated automatically into the installed app.
