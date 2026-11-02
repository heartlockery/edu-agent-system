# Stop local demo: kill uvicorn and cloudflared spawned by this project
$procs = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn app.main:app*') -or
  ($_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like '*trycloudflare*')
}
if (-not $procs) { Write-Host 'no running service found'; exit }
foreach ($p in $procs) {
  Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "stopped $($p.Name) pid=$($p.ProcessId)"
}
