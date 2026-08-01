$LOGOS_MODEL_PATH = if ($env:LOGOS_MODEL_PATH) { $env:LOGOS_MODEL_PATH } else { "D:\Models\logos-1b" }
$HOST = if ($env:HOST) { $env:HOST } else { "0.0.0.0" }
$PORT = if ($env:PORT) { [int]$env:PORT } else { 8080 }

function Test-VllmInstalled {
    try {
        $null = Get-Command python -ErrorAction Stop
        python -c "import vllm" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if (-not (Test-VllmInstalled)) {
    Write-Host "vLLM is not installed or not available in the current Python environment." -ForegroundColor Yellow
    Write-Host "Install it with:" -ForegroundColor Yellow
    Write-Host "  pip install vllm" -ForegroundColor Cyan
    exit 1
}

Write-Host "Starting LOGOS vLLM server..."
Write-Host "Model path: $LOGOS_MODEL_PATH"
Write-Host "API base: http://$HOST`:$PORT"

& python -m vllm.entrypoints.openai.api_server `
  --model "$LOGOS_MODEL_PATH" `
  --host "$HOST" `
  --port "$PORT" `
  --served-model-name logos-1b `
  --max-model-len 4096 `
  --trust-remote-code `
  --gpu-memory-utilization 0.85
