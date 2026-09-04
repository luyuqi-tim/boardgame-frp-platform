# Build Host exe on Windows (PowerShell) — browser UI only, no Client exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python -m pip install -U pip
python -m pip install -e .
python -m pip install pyinstaller

# Windows --add-data uses semicolon: source;dest
python -m PyInstaller --noconfirm --clean --onefile --console `
  --name BoardGameHost `
  --add-data "boardgame_platform\web;boardgame_platform\web" `
  --hidden-import boardgame_platform.games.tictactoe `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  packaging\run_host.py

Write-Host "Output:"
Get-ChildItem dist\BoardGameHost.exe
