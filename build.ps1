# MOPS Windows PowerShell 构建与集成测试脚本

Write-Host "Building MOPS Go binary (mops.exe)..." -ForegroundColor Green
go build -ldflags="-w -s" -o mops.exe ./cmd/mops
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build Failed!" -ForegroundColor Red
    exit 1
}

# 运行全量单元测试与二进制黑盒集成测试
Write-Host "Running unit & blackbox integration tests..." -ForegroundColor Cyan
go test -v -cover ./pkg/mops/...
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests failed!" -ForegroundColor Red
    exit 1
}

$size = (Get-Item mops.exe).Length / 1MB
Write-Host ("Build & Integration Tests PASSED! Output: mops.exe ({0:N2} MB)" -f $size) -ForegroundColor Green

