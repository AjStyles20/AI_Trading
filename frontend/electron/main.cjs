const { app, BrowserWindow, protocol, net } = require('electron');
const { dialog } = require('electron');
const path = require('path');
const { APP_ORIGIN, createProtocolHandler } = require('./protocol.cjs');
const { launchBackend } = require('./backend.cjs');

const isDev = process.env.NODE_ENV === 'development';
let backendChild;
let desktopToken;
if (!isDev) {
  protocol.registerSchemesAsPrivileged([{
    scheme: 'astral',
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  }]);
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    title: "Astral AI Desktop",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  let loadPromise;
  if (isDev) {
    // Vite dev server typically runs on 5173
    loadPromise = mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    loadPromise = mainWindow.loadURL(`${APP_ORIGIN}/`);
  }
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (isDev ? !url.startsWith('http://localhost:5173/') : !url.startsWith(`${APP_ORIGIN}/`)) {
      event.preventDefault();
    }
  });
  return { mainWindow, loadPromise };
}

const hasInstanceLock = app.requestSingleInstanceLock();
if (!hasInstanceLock) app.quit();

app.whenReady().then(async () => {
  if (!hasInstanceLock) return;
  if (app.isPackaged) {
    try {
      const started = await launchBackend({
        resourcesPath: process.resourcesPath,
        userDataPath: app.getPath('userData'),
      });
      backendChild = started.child;
      desktopToken = started.token;
      backendChild.once('exit', () => {
        if (!backendChild.killed) {
          dialog.showErrorBox('Astral AI backend stopped', 'The backend stopped unexpectedly. See the backend log in the application data folder.');
          app.quit();
        }
      });
    } catch (error) {
      dialog.showErrorBox('Astral AI could not start', error.message);
      app.quit();
      return;
    }
  }
  if (!isDev) {
    protocol.handle('astral', createProtocolHandler({
      net,
      distDir: path.join(__dirname, '../dist'),
      desktopToken,
    }));
  }
  const { mainWindow, loadPromise } = createWindow();
  if (app.isPackaged && process.argv.includes('--smoke-test')) {
    let exitCode = 1;
    try {
      await loadPromise;
      const passed = await mainWindow.webContents.executeJavaScript(`(async () => {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        const posted = await fetch('/api/strategy', {
          method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}',
        });
        const validation = await posted.json();
        const builderButton = Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === 'STRATEGY BUILDER');
        builderButton?.click();
        await new Promise(resolve => setTimeout(resolve, 300));
        const node = document.querySelector('.react-flow__node-input');
        const nodeStyle = node && getComputedStyle(node);
        return response.ok && Boolean(settings.theme) &&
          posted.status === 422 && validation.detail?.some(item => item.loc?.includes('prompt')) &&
          node?.textContent.includes('Start Strategy') && nodeStyle.backgroundColor !== 'rgb(255, 255, 255)' &&
          nodeStyle.color !== nodeStyle.backgroundColor &&
          Boolean(document.querySelector('#root')?.children.length);
      })()`);
      if (passed) exitCode = 0;
    } catch (error) {
      console.error('Desktop renderer smoke test failed:', error);
    }
    if (backendChild && !backendChild.killed) backendChild.kill();
    app.exit(exitCode);
    return;
  }

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  if (backendChild && !backendChild.killed) backendChild.kill();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});
