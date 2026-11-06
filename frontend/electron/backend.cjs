const fs = require('node:fs');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { spawn } = require('node:child_process');
const { createServer } = require('node:net');

const BACKEND_URL = 'http://127.0.0.1:8000/desktop/health';

function checkPortAvailable() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', () => reject(new Error('Port 8000 is occupied. Close the other service and retry.')));
    server.listen(8000, '127.0.0.1', () => server.close(resolve));
  });
}

async function launchBackend({ resourcesPath, userDataPath, fetchHealth = fetch, spawnProcess = spawn, checkPort = checkPortAvailable, timeoutMs = 90000 }) {
  const executable = path.join(resourcesPath, 'backend', 'astral-backend.exe');
  if (!fs.existsSync(executable)) throw new Error('Bundled Python backend is missing.');
  await checkPort();
  const dataDir = path.join(userDataPath, 'data');
  const logsDir = path.join(userDataPath, 'logs');
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(logsDir, { recursive: true });
  const token = randomBytes(32).toString('hex');
  const logFd = fs.openSync(path.join(logsDir, 'backend.log'), 'a');
  let child;
  try {
    child = spawnProcess(executable, [], {
      cwd: resourcesPath,
      windowsHide: true,
      env: { ...process.env, ASTRAL_DATA_DIR: dataDir, ASTRAL_DESKTOP_TOKEN: token },
      stdio: ['ignore', logFd, logFd],
    });
  } finally {
    fs.closeSync(logFd);
  }

  let exitDetail = null;
  child.once('error', (error) => { exitDetail = error.message; });
  child.once('exit', (code) => { exitDetail = `Backend exited with code ${code}`; });
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline && !exitDetail) {
    try {
      const response = await fetchHealth(BACKEND_URL, {
        headers: { 'x-astral-desktop-token': token },
        signal: AbortSignal.timeout(1500),
      });
      if (response.ok && (await response.json()).service === 'astral-backend') {
        return { child, token };
      }
    } catch { /* backend is still starting */ }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  if (!child.killed) child.kill();
  throw new Error(`${exitDetail || 'Backend startup timed out'}. See ${path.join(logsDir, 'backend.log')}`);
}

// Read-only phone gateway (see backend/phone_gateway.py). Off unless the user
// saved a Tailscale address in Settings; the address is checked again here
// rather than trusted from the file.
const PHONE_GATEWAY_CONFIG = 'phone_gateway.json';

function isTailscaleAddress(value) {
  const parts = String(value).split('.');
  if (parts.length !== 4 || !parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)) return false;
  return Number(parts[0]) === 100 && Number(parts[1]) >= 64 && Number(parts[1]) <= 127;
}

function readPhoneGatewayHost(dataDir) {
  try {
    const { host } = JSON.parse(fs.readFileSync(path.join(dataDir, PHONE_GATEWAY_CONFIG), 'utf8'));
    return typeof host === 'string' && isTailscaleAddress(host) ? host : null;
  } catch {
    return null;
  }
}

// Starts the gateway from the same bundled executable. Returns null when phone
// access is off or the executable or web app is missing; never throws.
function launchPhoneGateway({ resourcesPath, userDataPath, token, spawnProcess = spawn }) {
  const host = readPhoneGatewayHost(path.join(userDataPath, 'data'));
  if (!host) return null;
  const executable = path.join(resourcesPath, 'backend', 'astral-backend.exe');
  const distDir = path.join(resourcesPath, 'app.asar.unpacked', 'dist');
  if (!fs.existsSync(executable) || !fs.existsSync(path.join(distDir, 'index.html'))) return null;
  const logsDir = path.join(userDataPath, 'logs');
  fs.mkdirSync(logsDir, { recursive: true });
  const logFd = fs.openSync(path.join(logsDir, 'phone-gateway.log'), 'a');
  try {
    return spawnProcess(executable, ['--phone-gateway', '--host', host, '--dist', distDir], {
      cwd: resourcesPath,
      windowsHide: true,
      env: { ...process.env, ASTRAL_DATA_DIR: path.join(userDataPath, 'data'), ASTRAL_DESKTOP_TOKEN: token },
      stdio: ['ignore', logFd, logFd],
    });
  } catch {
    return null;
  } finally {
    fs.closeSync(logFd);
  }
}

module.exports = { launchBackend, launchPhoneGateway, readPhoneGatewayHost, isTailscaleAddress };
