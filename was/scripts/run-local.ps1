param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force .local | Out-Null
$dbPath = (Join-Path (Get-Location) '.local/saju-dictionary.db').Replace('\', '/')
$env:DATABASE_URL = "sqlite:///$dbPath"
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonPath)) { throw '먼저 Python 가상환경과 requirements.txt 의존성을 설치하세요.' }
& $pythonPath -m app.local_db
if ($LASTEXITCODE -ne 0) { throw '로컬 DB 초기화 실패' }
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port
