@echo off
chcp 65001 >nul

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator privileges for Windows Firewall...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo               MOPS Windows Firewall Setup
echo ========================================================
echo.

echo [1/4] Cleaning all existing mops firewall rules...
netsh advfirewall firewall delete rule name="MOPS Proxy Ports (TCP)" >nul 2>&1
netsh advfirewall firewall delete rule name="MOPS mDNS Port (UDP)" >nul 2>&1
netsh advfirewall firewall delete rule name="MOPS Go Toolchain (go.exe)" >nul 2>&1
netsh advfirewall firewall delete rule name="MOPS Executable (bin\mops.exe)" >nul 2>&1
netsh advfirewall firewall delete rule name="MOPS Test Binary (bin\mops.test.exe)" >nul 2>&1
echo      [+] Old MOPS firewall rules cleared!

echo [2/4] Adding TCP Firewall Rule for Ports 10080, 10081 & Test Range (profile=any)...
netsh advfirewall firewall add rule name="MOPS Proxy Ports (TCP)" dir=in action=allow protocol=TCP localport=10080,10081,10800-10899 profile=any >nul
echo      [+] TCP Ports (10080, 10081 and Test range 10800-10899) Allowed on ALL Profiles!

echo [3/4] Adding UDP Firewall Rule for Port 5353 (profile=any)...
netsh advfirewall firewall add rule name="MOPS mDNS Port (UDP)" dir=in action=allow protocol=UDP localport=5353 profile=any >nul
echo      [+] UDP Port 5353 Allowed on ALL Profiles!

echo [4/4] Adding Program Rules for Binaries in bin\ Directory (profile=any)...
for /f "tokens=*" %%g in ('where go 2^>nul') do set "GO_EXE=%%g"
if defined GO_EXE (
    netsh advfirewall firewall add rule name="MOPS Go Toolchain (go.exe)" dir=in action=allow program="%GO_EXE%" profile=any >nul
    echo      [+] Allowed Go Toolchain: %GO_EXE%
)

netsh advfirewall firewall add rule name="MOPS Executable (bin\mops.exe)" dir=in action=allow program="%~dp0bin\mops.exe" profile=any >nul
echo      [+] Allowed MOPS Binary: %~dp0bin\mops.exe

netsh advfirewall firewall add rule name="MOPS Test Binary (bin\mops.test.exe)" dir=in action=allow program="%~dp0bin\mops.test.exe" profile=any >nul
echo      [+] Allowed MOPS Test Binary: %~dp0bin\mops.test.exe

echo.
echo ========================================================
echo Setup Complete! All bin/ executables and ports allowed on ALL network profiles.
echo ========================================================
echo.
pause
