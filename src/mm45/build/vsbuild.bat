@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat" -arch=x64 >nul
cd /d "%~dp0%1"
msbuild scummvm.sln /m /p:Configuration=Release /p:Platform=x64 /v:minimal /nologo
