@echo off
set HTTP_PROXY=http://192.168.0.99:9999
set HTTPS_PROXY=http://192.168.0.99:9999

:: Optional: don't proxy local addresses
set NO_PROXY=localhost,127.0.0.1,10.,192.168.

echo.
cmd /k