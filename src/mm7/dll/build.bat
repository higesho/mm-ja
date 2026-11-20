@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
cl /nologo /O2 /W3 /MT /LD /utf-8 mm7jp.c /Fe:dinput.dll /link /DEF:dinput.def kernel32.lib advapi32.lib user32.lib
