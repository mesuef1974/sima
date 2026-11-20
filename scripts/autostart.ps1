# مُشغّل الدخول: ينتظر المهلة ثم يشغّل start_all.ps1 ويكتب مخرجاته في var/autostart.log. تسجّله install_autostart.ps1 ولا يُستدعى يدويًّا.
param([int]$DelaySeconds = 120)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "var\autostart.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null
"$(Get-Date -Format s) بدء بعد مهلة $DelaySeconds ثانية" | Set-Content -Path $log -Encoding utf8
Start-Sleep -Seconds $DelaySeconds
& (Join-Path $PSScriptRoot "start_all.ps1") *>> $log
"$(Get-Date -Format s) انتهى برمز $LASTEXITCODE" | Add-Content -Path $log -Encoding utf8
