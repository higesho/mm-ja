@echo off
rem build MM9 JP dinput.dll for release (no test hooks)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d %~dp0
if not exist ..\build\release mkdir ..\build\release
cl /nologo /O2 /MT /EHsc /utf-8 /W3 /LD /DMM9JP_RELEASE /Fo..\build\release\ /Fe..\build\release\dinput.dll dinput_proxy.cpp mm9jp.cpp jpfont.cpp testinput.cpp jpdict.cpp /link /DEF:dinput.def user32.lib gdi32.lib kernel32.lib
