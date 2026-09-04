# Build host + client exes on Windows (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python -m pip install -U pip
python -m pip install -e .
python -m pip install pyinstaller

python -m PyInstaller --noconfirm --clean --onefile --console `
  --name BoardGameHost `
  --hidden-import boardgame_platform.games.tictactoe `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  packaging\run_host.py

python -m PyInstaller --noconfirm --clean --onefile --console `
  --name BoardGameClient `
  --hidden-import boardgame_platform.games.tictactoe `
  packaging\run_client.py

Write-Host "Outputs:"
Get-ChildItem dist\BoardGameHost.exe, dist\BoardGameClient.exe
