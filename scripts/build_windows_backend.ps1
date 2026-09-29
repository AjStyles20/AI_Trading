$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python -m pip install -r backend/requirements.txt 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
python -m PyInstaller --noconfirm --clean --onedir --name astral-backend --paths . --paths backend --collect-all chromadb --collect-all onnxruntime --distpath frontend/backend-bundle --workpath build/pyinstaller --specpath build/pyinstaller backend/desktop_entry.py
if ($LASTEXITCODE -ne 0) { throw 'Backend bundle failed' }
