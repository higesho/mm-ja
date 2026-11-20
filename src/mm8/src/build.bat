@echo off
rem build mm8jp dll (32bit)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
if not exist ..\build mkdir ..\build
cl /nologo /O2 /W3 /MT /GS- /utf-8 /D_CRT_SECURE_NO_WARNINGS /LD mm8jp.c font.c testmode.c text.c /Fo..\build\ /Fe..\build\dinput.dll /link /DEF:mm8jp.def user32.lib kernel32.lib advapi32.lib
