# إعداد عزل النظام لاستدعاء النموذج (مرة واحدة، متساوي الأثر).
# وسم مستوى السلامة على ملف يحتاج حق WRITE_OWNER، وأذونات القرص لا تمنحه للحساب العادي. هذا السكربت يمنح حسابك
# ذلك الحق وحده على مجلد سِمة وما تحته. لا يمسّ مجلدًا آخر ولا إعداد نظام، ولا يحتاج مديرًا (أنت مالك الملفات).
#   & .\scripts\setup_isolation.ps1            المنح
#   & .\scripts\setup_isolation.ps1 -Remove    الإلغاء
param([switch]$Remove)

$root = Split-Path -Parent $PSScriptRoot
$me = "$env:USERDOMAIN\$env:USERNAME"
if ($Remove) {
    icacls $root /remove:g $me /Q | Out-Null
    Write-Host "أُلغي المنح الصريح لـ $me على $root."
} else {
    Write-Host "منح WRITE_OWNER لـ $me على $root وما تحته (قد يستغرق دقيقة)…"
    icacls $root /grant "${me}:(OI)(CI)(WO)" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "تعذّر المنح (رمز $LASTEXITCODE)."; exit 1 }
    Write-Host "تم."
}
icacls $root | Select-Object -First 8
