param([string]$InputPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
& python (Join-Path $PSScriptRoot 'CodexNutritionAdapter.py') $InputPath $OutputPath
exit $LASTEXITCODE
