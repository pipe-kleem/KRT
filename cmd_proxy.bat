@echo off
set HTTP_PROXY=http://192.168.0.180:8108
set HTTPS_PROXY=http://192.168.0.180:8108

:: Optional: don't proxy local addresses
set NO_PROXY=localhost,127.0.0.1,10.,192.168.

title Proxy Enabled (192.168.0.180:8108)
echo Proxy is set to 192.168.0.180:8108
echo.
cmd /k