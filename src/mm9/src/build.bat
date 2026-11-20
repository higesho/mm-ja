@echo off
rem build MM9 JP dinput.dll (32bit)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d %~dp0
if not exist ..\build mkdir ..\build
cl /nologo /O2 /MT /EHsc /utf-8 /W3 /LD /Fo..\build\ /Fe..\build\dinput.dll dinput_proxy.cpp mm9jp.cpp jpfont.cpp testinput.cpp jpdict.cpp /link /DEF:dinput.def user32.lib gdi32.lib kernel32.lib
