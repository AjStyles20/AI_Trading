const fs = require('node:fs');
const path = require('node:path');
const executable = path.join(__dirname, '../backend-bundle/astral-backend/astral-backend.exe');
if (!fs.existsSync(executable)) {
  throw new Error('Build the Windows Python backend bundle first: scripts/build_windows_backend.ps1');
}
