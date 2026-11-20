@echo off
rem ワールド・オブ・ジーン（マイト・アンド・マジック 4-5）日本語版を、同梱の ScummVM 非公式ビルドで起動します
cd /d "%~dp0"
if not exist "XEEN.CC" (
  echo このファイルは GOG 版 Might and Magic 4-5 のフォルダに置いてください。
  echo （XEEN.CC と DARK.CC がある場所です）
  pause
  exit /b 1
)
if not exist "xeen_ja.dat" (
  echo xeen_ja.dat が見つかりません。日本語化パッチのファイルを全部コピーしてください。
  pause
  exit /b 1
)
if not exist "SCUMMVM_SAVES_JP" mkdir "SCUMMVM_SAVES_JP"
start "" "ScummVM-XeenJP\scummvm.exe" -c "%~dp0ScummVM-XeenJP\scummvm-xeenjp.ini" --savepath="%~dp0SCUMMVM_SAVES_JP" --path="%~dp0." worldofxeen
