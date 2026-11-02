# Start local demo: uvicorn + cloudflared tunnel (detached via WMI, survives host process exit)
$Root = 'D:\desktop\edu-agent-system'
Set-Location $Root
New-Item -ItemType Directory -Force -Path "$Root\logs" | Out-Null
if (-not (Test-Path "$Root\data\edu.db")) {
  Write-Host 'Database not found, initializing...'
  & "$Root\.venv\Scripts\python.exe" "$Root\scripts\init_db.py"
}
$cmds = @("cmd.exe /c $Root\scripts\run_server.cmd", "cmd.exe /c $Root\scripts\run_tunnel.cmd")
foreach ($c in $cmds) {
  $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$c; CurrentDirectory=$Root}
  Write-Host "spawned pid=$($r.ProcessId) rc=$($r.ReturnValue)"
}
for ($i = 0; $i -lt 40; $i++) {
  try { $h = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 3; if ($h.ok) { Write-Host 'backend ready'; break } } catch { Start-Sleep -Seconds 2 }
}
Start-Sleep -Seconds 6
$log = Get-Content "$Root\logs\cloudflared.log" -Raw -ErrorAction SilentlyContinue
if ($log -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
  $u = $Matches[0]
  Set-Content -Path "$Root\logs\public_url.txt" -Value $u
  Write-Host "Public URL: $u"
} else {
  Write-Host 'Tunnel URL not found yet, check logs\cloudflared.log later'
}
