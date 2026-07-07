@echo off
REM NSSM service entry: run nginx from its install directory (handles paths with spaces).
cd /d "%~dp0"
nginx.exe -c conf\nginx.conf
