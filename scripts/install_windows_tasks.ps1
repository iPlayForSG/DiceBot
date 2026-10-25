param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+$')]
    [string]$QQ,
    [string]$Runtime
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $project '.venv\Scripts\pythonw.exe'
if (-not $Runtime) { $Runtime = Join-Path $project '.local-tools\napcat-runtime' }
$runtime = (Resolve-Path -LiteralPath $Runtime).Path
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if (-not (Test-Path -LiteralPath $python)) { throw "Python environment is missing: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'QQ.exe'))) { throw "Portable QQ is missing: $runtime" }

$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

$argument = ('"' + (Join-Path $project 'scripts\launch_napcat_portable.py') + '" --runtime "' + $runtime + '" --qq ' + $QQ)
$action = New-ScheduledTaskAction -Execute $python -Argument $argument -WorkingDirectory $project
if (Get-ScheduledTask -TaskName 'DiceBot NapCat' -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName 'DiceBot NapCat' -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
} else {
    Register-ScheduledTask -TaskName 'DiceBot NapCat' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Local QQ client connected to the cloud DiceBot.' | Out-Null
}
Write-Output ('NapCat task uses ' + $project)
