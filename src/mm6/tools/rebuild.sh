#!/bin/sh
# DLL を組み立て直し、データと一緒にゲームのフォルダへ置く（テスト中のゲームは止める）
cd "$(dirname "$0")/.."
python -X utf8 -I tools/mm6t.py kill >/dev/null 2>&1
powershell -NoProfile -Command "cmd /c '\"$(cygpath -w "$PWD")\dll\build.bat\"' 2>&1 | Select-String -Pattern 'error|warning' | ForEach-Object { \$_.Line }"
python -X utf8 -I tools/build.py | tail -3
