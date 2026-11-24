#!/bin/sh
# DLL を組み立て直し（配布版と試験版）、データと一緒にゲームのフォルダへ置く（置くのは試験版。テスト中のゲームは止める）
# テスト操作を使うには、ゲームのフォルダの mm6jp.ini に [Debug] Test=1 を足す
cd "$(dirname "$0")/.."
python -X utf8 -I tools/mm6t.py kill >/dev/null 2>&1
powershell -NoProfile -Command "cmd /c '\"$(cygpath -w "$PWD")\dll\build.bat\"' 2>&1 | Select-String -Pattern 'error|warning' | ForEach-Object { \$_.Line }"
powershell -NoProfile -Command "cmd /c '\"$(cygpath -w "$PWD")\dll\build.bat\" test' 2>&1 | Select-String -Pattern 'error|warning' | ForEach-Object { \$_.Line }"
python -X utf8 -I tools/build.py | tail -3
