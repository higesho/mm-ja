@echo off
rem ワールド・オブ・ジーン（マイト・アンド・マジック 4-5）CD 版（声付き）の日本語版を、同梱の ScummVM 非公式ビルドで起動します
cd /d "%~dp0"
if not exist "xeen_ja.dat" (
  echo xeen_ja.dat が見つかりません。日本語化パッチのファイルを全部コピーしてください。
  pause
  exit /b 1
)
if not exist "XEEN_CD\XEEN.CC" (
  if exist "GAME1.GOG" (
    echo GOG 版の CD イメージ（GAME1.GOG）から、CD 版のファイルを XEEN_CD フォルダに取り出します。
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ScummVM-XeenJP\prepare_cd.ps1" "%~dp0."
    if errorlevel 1 (
      pause
      exit /b 1
    )
  ) else (
    echo XEEN_CD フォルダに、CD 版の XEEN.CC・DARK.CC・INTRO.CC を置いてください。
    echo くわしくは「はじめにお読みください.txt」の「CD 版（声付き）で遊ぶには」を見てください。
    pause
    exit /b 1
  )
)
copy /y "xeen_ja.dat" "XEEN_CD\xeen_ja.dat" >nul
if not exist "SCUMMVM_SAVES_JP_CD" mkdir "SCUMMVM_SAVES_JP_CD"
start "" "ScummVM-XeenJP\scummvm.exe" -c "%~dp0ScummVM-XeenJP\scummvm-xeenjp.ini" --savepath="%~dp0SCUMMVM_SAVES_JP_CD" --path="%~dp0XEEN_CD" worldofxeen
