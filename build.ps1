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
Write-Host ("Build & Integration Tests PASSED! Output: bin/mops.exe ({0:N2} MB)" -f $size) -ForegroundColor Green
