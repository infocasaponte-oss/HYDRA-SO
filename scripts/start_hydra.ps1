# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
param([string]$Model = 'models/hydra-pilot/HYDRA.gguf', [int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$resolvedModel = (Resolve-Path -LiteralPath $Model).Path
$manifestPath = Join-Path (Split-Path $resolvedModel -Parent) 'build-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Missing build-manifest.json: build the candidate first.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$digest = (Get-FileHash -LiteralPath $resolvedModel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($digest -ne $manifest.sha256) { throw 'Model hash does not match build manifest.' }
New-Item -ItemType Directory -Force runtime | Out-Null
@"
FROM "$resolvedModel"
PARAMETER num_ctx 2048
PARAMETER temperature 0
"@ | Set-Content -LiteralPath runtime/HYDRA.Modelfile -Encoding utf8
ollama create hydra-local -f runtime/HYDRA.Modelfile
if ($LASTEXITCODE -ne 0) { throw 'Ollama model import failed.' }
$env:HYDRA_MODELS_CONFIG = 'config/models.hydra.yaml'
$env:HYDRA_OFFLINE = 'false'
$env:HYDRA_BUDGET_TIME_SCALE = '6'
$env:HYDRA_SANDBOX_BACKEND = 'docker'
py -3.12 -m hydra.cli serve --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw 'HYDRA gateway failed.' }
