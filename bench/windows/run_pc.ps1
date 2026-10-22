# Full protocol for the PC condition. Identical arguments to the Mac runs.
Set-Location (Join-Path $PSScriptRoot "..\..")
$py = ".\.venv\Scripts\python.exe"
& $py bench\run.py --condition pc_rtx4060 --task throughput --set pilot --concurrency 1 4 16 --repeats 2
& $py bench\run.py --condition pc_rtx4060 --task quality    --set pilot --concurrency 4 --repeats 1
& $py bench\run.py --condition pc_rtx4060 --task throughput --set main  --concurrency 1 4 16 --repeats 3
& $py bench\run.py --condition pc_rtx4060 --task quality    --set main  --concurrency 4 --repeats 2
& $py bench\summarize.py
