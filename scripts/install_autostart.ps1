# يسجّل تشغيل سِمة (القاعدة ثم LM Studio ثم المنصة على 127.0.0.1) بعد دخول ويندوز بمهلة، بلا نافذة ظاهرة.
# الاستعمال: pwsh scripts/install_autostart.ps1 [-DelayMinutes 2] [-Remove]
# يسجّل مهمة مجدولة للمستخدم الحالي «Sima Platform»؛ وإن رُفضت بلا صلاحية مدير وضع اختصارًا في مجلد بدء التشغيل للمستخدم.
# الإيقاف: Stop-ScheduledTask -TaskName "Sima Platform"، والإزالة: -Remove. المخرجات في var/autostart.log.
param([int]$DelayMinutes = 2, [switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "Sima Platform"
$root = Split-Path -Parent $PSScriptRoot
$link = Join-Path ([Environment]::GetFolderPath("Startup")) "$name.lnk"

if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }
if (Test-Path $link) { Remove-Item $link }
if ($Remove) { Write-Host "أُزيل التشغيل التلقائي لسِمة."; exit 0 }

$pwsh = (Get-Command pwsh).Source
$launcher = Join-Path $PSScriptRoot "autostart.ps1"
$seconds = $DelayMinutes * 60
# conhost --headless: لا نافذة طرفية حتى مع Windows Terminal طرفيةً افتراضية
$arguments = "--headless `"$pwsh`" -NoProfile -NoLogo -ExecutionPolicy Bypass -File `"$launcher`" -DelaySeconds $seconds"

try {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arguments -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "سُجّلت المهمة المجدولة «$name»: تبدأ بعد $DelayMinutes دقيقة من دخولك ويندوز."
} catch {
    Write-Warning "تعذّر تسجيل المهمة المجدولة ($($_.Exception.Message)): يُستعمل مجلد بدء التشغيل."
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = Join-Path $env:SystemRoot "System32\conhost.exe"
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $root
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Host "وُضع اختصار «$name» في مجلد بدء التشغيل: يبدأ بعد $DelayMinutes دقيقة من دخولك ويندوز."
}
