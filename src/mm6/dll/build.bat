@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d %~dp0
if not exist out mkdir out
cl /nologo /O1 /MT /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS /LD main.c text.c jpfont.c lodtext.c ddwin.c misc.c /Fo:out\ /Fe:out\ddraw.dll /link /DEF:ddraw.def user32.lib gdi32.lib advapi32.lib
