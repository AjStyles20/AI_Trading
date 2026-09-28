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

`npm run electron:build` can package the renderer, but the Python backend and its dependencies are **not** embedded. The resulting installer is not a standalone release. A Windows release still needs backend packaging, installer lifecycle, and an on-device smoke test.
