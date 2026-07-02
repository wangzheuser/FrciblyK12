@echo off
REM aBaiAutoplus 开发模式启动脚本快捷方式
REM Author: wangqiupei

setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-start.ps1" %*
endlocal
