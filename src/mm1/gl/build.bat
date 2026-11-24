@echo off
rem opengl32.dll（DOSBox の DOSBOX フォルダに置く代わり）を組み立てる。
rem   build.bat       … 配布版 out\opengl32.dll
rem   build.bat test  … 試験版 out\test\opengl32.dll（/DUJ_TEST、dump=1 で絵を BMP に保存する）。配布しない。
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul 2>nul
cd /d "%~dp0"
set O=obj\release
set OUT=out\opengl32.dll
set DEF=
if "%1"=="test" (
  set O=obj\test
  set OUT=out\test\opengl32.dll
  set DEF=/DUJ_TEST
)
if not exist %O% mkdir %O%
if not exist out\test mkdir out\test
rc /nologo /fo %O%\mmgl.res mmgl.rc || exit /b 1
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS %DEF% /O2 /LD /MT /W3 /Fo%O%\ gl_proxy.c %O%\mmgl.res /Fe%OUT% /link /IMPLIB:%O%\opengl32.lib user32.lib gdi32.lib kernel32.lib || exit /b 1
del %O%\opengl32.exp 2>nul
