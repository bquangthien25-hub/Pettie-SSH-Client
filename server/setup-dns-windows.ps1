# Cài DNS mặc định cho Pettie SSH Client (Windows server / client)
# Chạy: powershell -ExecutionPolicy Bypass -File setup-dns-windows.ps1

$ErrorActionPreference = "Stop"
$domain = "trungtamanninhmang.xyz"
$dir = Join-Path $env:USERPROFILE ".pettie-server"

New-Item -ItemType Directory -Force -Path $dir | Out-Null

$hostFile = Join-Path $dir "dns.host"
$jsonFile = Join-Path $dir "dns.json"

Set-Content -Path $hostFile -Value $domain -Encoding UTF8
@{
    host = $domain
} | ConvertTo-Json | Set-Content -Path $jsonFile -Encoding UTF8

Write-Host "Da tao DNS cho Pettie:" -ForegroundColor Green
Write-Host "  $hostFile"
Write-Host "  $jsonFile"
Write-Host "  Domain: $domain"
