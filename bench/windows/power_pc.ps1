# Logs GPU power draw once per second to runs/pc_rtx4060/power_<timestamp>.csv
$dir = Join-Path $PSScriptRoot "..\..\runs\pc_rtx4060"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$out = Join-Path $dir ("power_" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".csv")
Write-Host "logging to $out (Ctrl+C to stop)"
nvidia-smi --query-gpu=timestamp,power.draw,utilization.gpu,memory.used,temperature.gpu --format=csv -l 1 | Tee-Object -FilePath $out
