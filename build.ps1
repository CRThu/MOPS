# MOPS Windows PowerShell 构建与集成测试脚本

if (-not (Test-Path "bin")) {
    New-Item -ItemType Directory -Path "bin" | Out-Null
}

Write-Host "Building MOPS Go binary (bin/mops.exe)..." -ForegroundColor Green
go build -ldflags="-w -s" -o bin/mops.exe ./cmd/mops
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build Failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Compiling test binary (bin/mops.test.exe)..." -ForegroundColor Cyan
go test -c -o bin/mops.test.exe ./pkg/mops
if ($LASTEXITCODE -ne 0) {
    Write-Host "Test compilation failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Running unit & blackbox integration tests..." -ForegroundColor Cyan
cmd /c "bin\mops.test.exe -test.v"
$testStatus = $LASTEXITCODE

if ($testStatus -ne 0) {
    Write-Host "Tests failed!" -ForegroundColor Red
    exit 1
}

$size = (Get-Item bin/mops.exe).Length / 1MB
Write-Host ("Go Backend & Integration Tests PASSED! Output: bin/mops.exe ({0:N2} MB)" -f $size) -ForegroundColor Green

Write-Host "Building Tauri GUI Desktop Widget (mops-gui.exe)..." -ForegroundColor Green
Push-Location gui
bun tauri build
$guiBuildStatus = $LASTEXITCODE
Pop-Location

if ($guiBuildStatus -ne 0) {
    Write-Host "Tauri GUI Build Failed!" -ForegroundColor Red
    exit 1
}

$portableDir = "bin/MOPS-Portable"
if (-not (Test-Path $portableDir)) {
    New-Item -ItemType Directory -Path $portableDir | Out-Null
}

Copy-Item -Path "bin/mops.exe" -Destination "$portableDir/mops.exe" -Force
Copy-Item -Path "gui/src-tauri/target/release/mops-gui.exe" -Destination "$portableDir/MOPS Desktop.exe" -Force

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "MOPS Desktop Portable Build Succeeded!" -ForegroundColor Green
Write-Host "Portable package created at: $portableDir/" -ForegroundColor Yellow
Write-Host "  ├── MOPS Desktop.exe  (Desktop Widget UI)" -ForegroundColor Cyan
Write-Host "  └── mops.exe          (Go Proxy Backend)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green

