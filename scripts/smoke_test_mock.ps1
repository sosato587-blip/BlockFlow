# Smoke test for mock mode BlockFlow backend.
# Usage:
#   $env:BLOCKFLOW_MOCK_RUNPOD = "1"; uv run app.py --port 8100  # in another terminal
#   .\scripts\smoke_test_mock.ps1

$ErrorActionPreference = "Stop"
$BASE = "http://localhost:8100"

function Test-Endpoint($name, $method, $path, $body) {
  Write-Host "→ $name" -ForegroundColor Cyan
  try {
    if ($method -eq "GET") {
      $resp = Invoke-RestMethod -Uri "$BASE$path" -Method GET
    } else {
      $resp = Invoke-RestMethod -Uri "$BASE$path" -Method $method -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 10)
    }
    if ($resp.ok -eq $true -or $resp.status -ne $null) {
      Write-Host "  OK: $($resp | ConvertTo-Json -Depth 2 -Compress)" -ForegroundColor Green
    } else {
      Write-Host "  UNEXPECTED: $($resp | ConvertTo-Json -Depth 2 -Compress)" -ForegroundColor Yellow
    }
  } catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
  }
}

Test-Endpoint "health"          "GET"  "/api/m/health" $null
Test-Endpoint "outpaint"        "POST" "/api/m/outpaint" @{
  image_url = "https://example.com/fake.png"
  prompt    = "full body, detailed background"
  pad_left  = 256; pad_right = 256; pad_top = 0; pad_bottom = 256
  feathering = 40; steps = 20; denoise = 1.0
}
Test-Endpoint "character_sheet" "POST" "/api/m/character_sheet" @{
  prompt = "1girl, silver hair, blue eyes, school uniform"
  width = 2048; height = 1024; steps = 30
}
Test-Endpoint "ltx_video_t2v"   "POST" "/api/m/ltx_video" @{
  prompt = "a cat walking in a neon-lit alley, cinematic"
  width = 768; height = 512; length = 97; fps = 25; steps = 30
}
Test-Endpoint "ltx_video_i2v"   "POST" "/api/m/ltx_video" @{
  prompt = "the subject turns and smiles"
  image_url = "https://example.com/fake.png"
  width = 768; height = 512; length = 97; fps = 25; steps = 30
}
Test-Endpoint "ltx_dl_info"     "GET"  "/api/m/ltx_dl_info" $null

Write-Host "`nDone. If all endpoints returned 'ok': true with mock- job ids, mock mode is healthy." -ForegroundColor Cyan
