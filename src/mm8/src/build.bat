@echo off
rem MM8 日本語化の dinput.dll を組み立てる（32 ビット）
rem   build.bat       … 配布版 ..\build\dinput.dll
rem   build.bat test  … 試験版 ..\build\test\dinput.dll（/DMM8JP_TEST と testmode.c を足す。tools\mm8_ctl.py が使う）。配布しない。
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
set O=..\build\obj\release
set OUT=..\build\dinput.dll
set DEF=
set EXTRA=
if "%1"=="test" (
  set O=..\build\obj\test
  set OUT=..\build\test\dinput.dll
  set DEF=/DMM8JP_TEST
  set EXTRA=testmode.c
)
if not exist %O% mkdir %O%
if not exist ..\build\test mkdir ..\build\test
rc /nologo /fo %O%\mm8jp.res mm8jp.rc || exit /b 1
cl /nologo /O2 /W3 /MT /GS- /utf-8 /D_CRT_SECURE_NO_WARNINGS %DEF% /LD mm8jp.c font.c text.c %EXTRA% %O%\mm8jp.res /Fo%O%\ /Fe%OUT% /link /DEF:mm8jp.def /IMPLIB:%O%\dinput.lib user32.lib kernel32.lib advapi32.lib || exit /b 1
del %O%\dinput.exp 2>nul
