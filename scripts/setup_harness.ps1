$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $project '.local-tools\harness'
& npm.cmd install --prefix $runtime '@deepseek-ai/dsh@0.2.1-rc.2' --omit=dev --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Harness installation failed' }
Write-Output 'Harness runtime installed in the ignored project-local directory.'
