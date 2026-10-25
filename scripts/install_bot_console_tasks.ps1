$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$entries = @(
    @{Name='DiceBot Console';Python='.venv\Scripts\pythonw.exe';Script='scripts\run_bot_console.py'},
    @{Name='DiceBot AstrBot';Python='.local-tools\astrbot\venv\Scripts\pythonw.exe';Script='scripts\run_astrbot.py'}
)
foreach ($entry in $entries) {
    $python = Join-Path $project $entry.Python
    $script = Join-Path $project $entry.Script
    if (-not (Test-Path -LiteralPath $python)) { throw ('Python environment missing: ' + $python) }
    $existing = Get-ScheduledTask -TaskName $entry.Name -ErrorAction SilentlyContinue
    if ($existing -and $existing.Actions.Arguments -ne ('"' + $script + '"')) { throw 'Task belongs to an unexpected configuration' }
    $action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $script + '"') -WorkingDirectory $project
    # 两个任务各自受 Windows 管理，关闭浏览器或 Codex 不影响 Bot 的生命周期。
    Register-ScheduledTask -TaskName $entry.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
}
Start-ScheduledTask -TaskName 'DiceBot Console'
