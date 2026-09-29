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
