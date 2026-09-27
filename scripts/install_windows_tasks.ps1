param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+$')]
    [string]$QQ
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $project '.venv\Scripts\python.exe'
$runtime = Join-Path (Split-Path $project -Parent) 'NapCatRuntime'
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

$tasks = @(
    @{
        Name = 'DiceBot Stack'
        Argument = ('"' + (Join-Path $project 'scripts\run_quick_demo.py') + '"')
        Description = 'QQ tabletop API, bot, Quick Tunnel, and GitHub Pages URL updates.'
    },
    @{
        Name = 'DiceBot NapCat'
        Argument = ('"' + (Join-Path $project 'scripts\launch_napcat_portable.py') + '" --runtime "' + $runtime + '" --qq ' + $QQ)
        Description = 'Portable NapCat QQ client for DiceBot.'
    }
)

foreach ($task in $tasks) {
    if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
        Write-Output "Existing task preserved: $($task.Name)"
        continue
    }
    $action = New-ScheduledTaskAction -Execute $python -Argument $task.Argument -WorkingDirectory $project
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $task.Description | Out-Null
    Write-Output "Installed task: $($task.Name)"
}
