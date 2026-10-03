# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
# Serves the hash-pinned HYDRA v8 GGUF as Hyd's embedding encoder (mean pooling) on 127.0.0.1:$Port.
param([int]$Port = 18094)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$binary = Join-Path $root 'runtime/llama-cuda-b11146/llama-server.exe'
$model = Join-Path $root 'models/hydra-instruction-v8/HYDRA.gguf'
if (!(Test-Path -LiteralPath $binary)) { throw 'Missing pinned CUDA runtime b11146' }
if (!(Test-Path -LiteralPath $model)) { throw 'Missing HYDRA v8 GGUF' }
if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLower() -ne '0ef14148ababf98c52623f164d776ed76f17a583175ea91301e024a157231761') { throw 'GGUF hash mismatch' }
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port already in use" }
Start-Process -FilePath $binary -WorkingDirectory $root -WindowStyle Hidden -ArgumentList @('--model', $model, '--alias', 'hydra-instruction-v8', '--host', '127.0.0.1', '--port', "$Port", '--ctx-size', '2048', '--n-gpu-layers', '99', '--parallel', '1', '--embeddings', '--pooling', 'mean') -RedirectStandardOutput (Join-Path $root 'runtime/hyd-encoder.stdout.log') -RedirectStandardError (Join-Path $root 'runtime/hyd-encoder.stderr.log') -PassThru
