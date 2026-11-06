const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { launchBackend } = require('./backend.cjs');

test('bundled backend starts with writable data and a private health token', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'astral-launch-'));
  try {
    const executable = path.join(root, 'resources', 'backend', 'astral-backend.exe');
    fs.mkdirSync(path.dirname(executable), { recursive: true });
    fs.writeFileSync(executable, 'test');
    let spawned;
    const child = new EventEmitter();
    child.kill = () => { child.killed = true; };
    const result = await launchBackend({
      resourcesPath: path.join(root, 'resources'),
      userDataPath: path.join(root, 'user'),
      checkPort: async () => {},
      spawnProcess: (file, _args, options) => { spawned = { file, options }; return child; },
      fetchHealth: async (_url, options) => {
        assert.equal(options.headers['x-astral-desktop-token'], spawned.options.env.ASTRAL_DESKTOP_TOKEN);
        return { ok: true, json: async () => ({ service: 'astral-backend' }) };
      },
    });
    assert.equal(spawned.file, executable);
    assert.equal(spawned.options.env.ASTRAL_DATA_DIR, path.join(root, 'user', 'data'));
    assert.equal(result.token.length, 64);
    assert.equal(result.child, child);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

const { launchPhoneGateway, isTailscaleAddress } = require('./backend.cjs');

function phoneSetup(config) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'astral-phone-'));
  const resources = path.join(root, 'resources');
  fs.mkdirSync(path.join(resources, 'backend'), { recursive: true });
  fs.writeFileSync(path.join(resources, 'backend', 'astral-backend.exe'), 'test');
  fs.mkdirSync(path.join(resources, 'app.asar.unpacked', 'dist'), { recursive: true });
  fs.writeFileSync(path.join(resources, 'app.asar.unpacked', 'dist', 'index.html'), '<html></html>');
  fs.mkdirSync(path.join(root, 'user', 'data'), { recursive: true });
  if (config !== undefined) fs.writeFileSync(path.join(root, 'user', 'data', 'phone_gateway.json'), config);
  return { root, resources, user: path.join(root, 'user') };
}

test('phone gateway starts only for a saved Tailscale address, with the session token', () => {
  const setup = phoneSetup(JSON.stringify({ host: '100.101.102.103' }));
  try {
    let spawned;
    const child = launchPhoneGateway({
      resourcesPath: setup.resources,
      userDataPath: setup.user,
      token: 'session-token',
      spawnProcess: (file, args, options) => { spawned = { file, args, options }; return { pid: 1 }; },
    });
    assert.deepEqual(child, { pid: 1 });
    assert.deepEqual(spawned.args, ['--phone-gateway', '--host', '100.101.102.103', '--dist', path.join(setup.resources, 'app.asar.unpacked', 'dist')]);
    assert.equal(spawned.options.env.ASTRAL_DESKTOP_TOKEN, 'session-token');
    assert.equal(spawned.options.env.ASTRAL_DATA_DIR, path.join(setup.user, 'data'));
  } finally {
    fs.rmSync(setup.root, { recursive: true, force: true });
  }
});

test('phone gateway stays off without a valid Tailscale address', () => {
  for (const config of [undefined, '{broken', JSON.stringify({ host: '0.0.0.0' }), JSON.stringify({ host: '192.168.1.5' }),
    JSON.stringify({ host: '127.0.0.1' }), JSON.stringify({ host: '100.128.0.1' }), JSON.stringify({ host: null })]) {
    const setup = phoneSetup(config);
    try {
      const result = launchPhoneGateway({
        resourcesPath: setup.resources,
        userDataPath: setup.user,
        token: 't',
        spawnProcess: () => { throw new Error('must not start'); },
      });
      assert.equal(result, null, `config ${config}`);
    } finally {
      fs.rmSync(setup.root, { recursive: true, force: true });
    }
  }
});

test('Tailscale address check matches the backend rule', () => {
  for (const ok of ['100.64.0.1', '100.127.255.255']) assert.equal(isTailscaleAddress(ok), true);
  for (const bad of ['100.63.255.255', '100.128.0.0', '1.2.3.4', '100.64.0', '100.64.0.256']) assert.equal(isTailscaleAddress(bad), false);
});
