@echo off
rem 引数なし: 配布版 dinput.dll（このフォルダ）を作る
rem build.bat test: 試験版（/DMM7JP_TEST、test\dinput.dll）を作る。試験版は配布しない
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
set O=obj\release
set OUT=dinput.dll
set DEF=
if "%1"=="test" (
  set O=obj\test
  set OUT=test\dinput.dll
  set DEF=/DMM7JP_TEST
  if not exist test mkdir test
)
if not exist %O% mkdir %O%
rc /nologo /fo %O%\mm7jp.res mm7jp.rc || exit /b 1
cl /nologo /O2 /W3 /MT /LD /utf-8 %DEF% /Fo%O%\ mm7jp.c %O%\mm7jp.res /Fe:%OUT% /link /DEF:dinput.def /IMPLIB:%O%\dinput.lib kernel32.lib advapi32.lib user32.lib || exit /b 1
