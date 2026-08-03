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

echo [1/3] Cleaning all existing mops firewall rules...
netsh advfirewall firewall delete rule name="MOPS Proxy Ports (TCP)" >nul 2>&1
netsh advfirewall firewall delete rule name="MOPS mDNS Port (UDP)" >nul 2>&1
echo      [+] Old MOPS firewall rules cleared!

echo [2/3] Adding TCP Firewall Rule (Ports: 10080, 10081, 10800-10899)...
netsh advfirewall firewall add rule name="MOPS Proxy Ports (TCP)" dir=in action=allow protocol=TCP localport=10080,10081,10800-10899 >nul
echo      [+] TCP Ports (10080, 10081 and Test range 10800-10899) Allowed successfully!

echo [3/3] Adding UDP Firewall Rule (Port: 5353)...
netsh advfirewall firewall add rule name="MOPS mDNS Port (UDP)" dir=in action=allow protocol=UDP localport=5353 >nul
echo      [+] UDP Port 5353 Allowed successfully!

echo.
echo ========================================================
echo Setup Complete! Ports (TCP 10080, 10081, 10800-10899 and UDP 5353) allowed.
echo ========================================================
echo.
pause
