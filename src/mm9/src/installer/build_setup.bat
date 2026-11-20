@echo off
rem build MM9JP.exe (installer). mm9jp.dlt must be in this folder.
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d %~dp0
rc /nologo mm9jp_setup.rc
cl /nologo /O2 /MT /utf-8 /EHsc mm9jp_setup.cpp mm9jp_setup.res /Fe:MM9JP.exe /link kernel32.lib
