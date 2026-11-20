# يشغّل ما تحتاجه سِمة بترتيبه: قاعدة البيانات، ثم خادم LM Studio المحلي (للتضمين فقط)، ثم المنصة في هذه الطرفية.
# الاستعمال: pwsh scripts/start_all.ps1 [-NoLms] [-Port 8766]
# كل شيء على 127.0.0.1. يُعاد تشغيله بأمان: ما كان يعمل لا يُعاد.
param([switch]$NoLms, [int]$Port = 8766)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "1/3 قاعدة سِمة…"
uv run sima db start
# المنصة تحتمل قاعدة متوقفة وتعرض حالها؛ فشل القاعدة لا يمنع بدءها عند الدخول (م9)
if ($LASTEXITCODE -ne 0) { Write-Warning "تعذّر تشغيل القاعدة: تبدأ المنصة بدونها وتعرض حالها. شغّلها لاحقًا بـ uv run sima db start" }

if (-not $NoLms) {
    $lms = Get-Command lms -ErrorAction SilentlyContinue
    if ($lms) {
        Write-Host "2/3 خادم LM Studio (التضمين المحلي)…"
        try { & lms server start --port 1234 --bind 127.0.0.1 2>&1 | Out-Host } catch { Write-Warning "تعذّر تشغيل LM Studio: يُتجاوز فحص الجِدّة" }
    } else {
        Write-Warning "أمر lms غير موجود: يُتجاوز فحص جِدّة الأفكار (SIMA_EMBED=0 يتجاوزه صراحةً)"
    }
} else {
    Write-Host "2/3 تُخطّى LM Studio (-NoLms)"
}

# مقبس بقي لحظات بعد إغلاق طرفية المنصة كان يُحسب منصة تعمل: لا يُعتدّ به إلا إن كانت عمليته حيّة
$listen = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listen -and (Get-Process -Id $listen.OwningProcess -ErrorAction SilentlyContinue)) {
    Write-Host "3/3 المنصة تعمل سلفًا على http://127.0.0.1:$Port"
    exit 0
}
Write-Host "3/3 المنصة على http://127.0.0.1:$Port (Ctrl+C للإيقاف)"
uv run sima board --port $Port
