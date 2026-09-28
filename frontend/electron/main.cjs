const { app, BrowserWindow, protocol, net } = require('electron');
const path = require('path');
const { APP_ORIGIN, createProtocolHandler } = require('./protocol.cjs');

const isDev = process.env.NODE_ENV === 'development';
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

  if (isDev) {
    // Vite dev server typically runs on 5173
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadURL(`${APP_ORIGIN}/`);
  }
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (isDev ? !url.startsWith('http://localhost:5173/') : !url.startsWith(`${APP_ORIGIN}/`)) {
      event.preventDefault();
    }
  });
}

app.whenReady().then(() => {
  if (!isDev) {
    protocol.handle('astral', createProtocolHandler({
      net,
      distDir: path.join(__dirname, '../dist'),
    }));
  }
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});
