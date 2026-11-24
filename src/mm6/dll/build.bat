@echo off
rem 引数なし: 配布版 out\ddraw.dll ／ build.bat test: 試験版 out\test\ddraw.dll（テスト操作入り。配布しない）
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d %~dp0
set O=out\obj
set OUT=out\ddraw.dll
set DEF=
if "%1"=="test" (
  set O=out\test\obj
  set OUT=out\test\ddraw.dll
  set DEF=/DMM6JP_TEST
)
if not exist %O% mkdir %O%
rc /nologo /fo %O%\mm6jp.res mm6jp.rc || exit /b 1
cl /nologo /O1 /MT /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS %DEF% /LD main.c text.c jpfont.c lodtext.c ddwin.c misc.c %O%\mm6jp.res /Fo:%O%\ /Fe:%OUT% /link /DEF:ddraw.def /IMPLIB:%O%\ddraw.lib user32.lib gdi32.lib advapi32.lib || exit /b 1
