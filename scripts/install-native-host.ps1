param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-p]{32}$')][string]$ExtensionId,
    [string]$InstallRoot
)
$ErrorActionPreference = 'Stop'
if (-not $InstallRoot) {
    $adjacentHost = Join-Path $PSScriptRoot 'EasyMP3Host.exe'
    if (Test-Path -LiteralPath $adjacentHost) {
        $InstallRoot = $PSScriptRoot
    } else {
        $InstallRoot = "$env:LOCALAPPDATA\EasyMP3\native-host"
    }
}
$root = [IO.Path]::GetFullPath($InstallRoot)
$hostExe = Join-Path $root 'EasyMP3Host.exe'
$manifest = Join-Path $root 'com.easymp3.host.json'
if (-not (Test-Path -LiteralPath $hostExe)) { throw "Missing helper: $hostExe" }
$manifestData = @{ name='com.easymp3.host'; description='EasyMP3 Chrome Native Messaging host'; path=$hostExe; type='stdio'; allowed_origins=@("chrome-extension://$ExtensionId/") } | ConvertTo-Json -Compress
[IO.File]::WriteAllText($manifest, $manifestData, [Text.UTF8Encoding]::new($false))
$key = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.easymp3.host'
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name '(default)' -Value $manifest
Write-Host "Installed EasyMP3 native host for $ExtensionId"
