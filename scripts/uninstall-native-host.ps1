Remove-Item -LiteralPath 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.easymp3.host' -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Removed EasyMP3 native host registration.'
