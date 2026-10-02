# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
# Serves the v8 generalist on $Port; with -GroundedSpecialist also the v5 grounded specialist on $SpecialistPort.
param([int]$Port = 18090, [switch]$GroundedSpecialist, [int]$SpecialistPort = 18092)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $root 'runtime/llama-cuda-b11146/llama-server.exe'
if (!(Test-Path -LiteralPath $binary)) { throw 'Missing pinned CUDA runtime b11146' }
$devices = (& $binary --list-devices 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $devices -notmatch 'CUDA') { throw "CUDA unavailable: $devices" }

function Start-Hydra([string]$Relative, [string]$Sha256, [string]$Alias, [int]$ServePort, [int]$Context, [string]$Log) {
    $model = Join-Path $root $Relative
    if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLower() -ne $Sha256) { throw "GGUF hash mismatch: $Relative" }
    Start-Process -FilePath $binary -WorkingDirectory $root -WindowStyle Hidden -ArgumentList @('--model', $model, '--alias', $Alias, '--host', '127.0.0.1', '--port', "$ServePort", '--ctx-size', "$Context", '--n-gpu-layers', '99', '--parallel', '1', '--jinja') -RedirectStandardOutput (Join-Path $root "runtime/$Log.stdout.log") -RedirectStandardError (Join-Path $root "runtime/$Log.stderr.log") -PassThru
}

Start-Hydra 'models/hydra-instruction-v8/HYDRA.gguf' '0ef14148ababf98c52623f164d776ed76f17a583175ea91301e024a157231761' 'hydra-instruction-v8' $Port 2048 'hydra-direct'
if ($GroundedSpecialist) {
    Start-Hydra 'models/hydra-program-v5-grounded/HYDRA.gguf' '3442f057df020309dd80431c797fda7390135d14be575be5a328275077e6c987' 'hydra-program-v5-grounded' $SpecialistPort 4096 'hydra-grounded'
}
