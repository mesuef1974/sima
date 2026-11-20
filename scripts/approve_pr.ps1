<#
سطر اعتماد المالك على طلب دمج، يشغّله المالك بنفسه بعد مراجعة الطلب (سِمة تعرض الأمر ولا تشغّله).

    & 'D:\sima\scripts\approve_pr.ps1' -Repo mesuef1974/math_papers -Pr 2 -Head 06b0e961

يرفض إن تغيّر رأس الطلب عمّا راجعته، ويستبدل السطر النموذجي «(يُكتب سطر الاعتماد هنا…)» أو يضيف السطر في آخر الوصف.
الصيغة هي ما يفحصه approval-head في المشروع: اعتُمد من المالك — <التاريخ> — الرأس <sha>
#>
param(
    [Parameter(Mandatory)] [ValidatePattern('^[\w.-]+/[\w.-]+$')] [string] $Repo,
    [Parameter(Mandatory)] [int] $Pr,
    [Parameter(Mandatory)] [ValidatePattern('^[0-9a-f]{7,40}$')] [string] $Head
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$current = gh pr view $Pr -R $Repo --json headRefOid -q .headRefOid
if (-not $current.StartsWith($Head)) {
    throw "رأس الطلب الآن $($current.Substring(0, 8)) لا $Head؛ راجع التغييرات الجديدة ثم خذ الأمر المحدّث من سِمة."
}
$body = (gh pr view $Pr -R $Repo --json body -q .body) -join "`n"
$line = "اعتُمد من المالك — $(Get-Date -Format 'yyyy-MM-dd') — الرأس $($Head.Substring(0, 8))"
if ($body -match "اعتُمد من المالك — \d{4}-\d{2}-\d{2} — الرأس $($Head.Substring(0, 7))") {
    Write-Host "الطلب $Pr معتمد سابقًا على هذا الرأس؛ لا تغيير."
    exit 0
}
$placeholder = '(?m)^\(يُكتب سطر الاعتماد هنا.*\)\s*$'
$new = if ($body -match $placeholder) { [regex]::Replace($body, $placeholder, $line) } else { "$body`n`n$line" }
$tmp = New-TemporaryFile
try {
    [IO.File]::WriteAllText($tmp, $new, [Text.UTF8Encoding]::new($false))
    gh pr edit $Pr -R $Repo --body-file $tmp | Out-Null
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
Write-Host "كُتب سطر اعتمادك في وصف الطلب $Pr ($Repo): $line"
Write-Host "يُعاد فحص approval-head آليًا الآن."
