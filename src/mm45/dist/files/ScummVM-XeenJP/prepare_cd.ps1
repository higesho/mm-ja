# GOG 版の CD イメージ（GAME1.GOG）から、CD 版の XEEN.CC・DARK.CC・INTRO.CC を XEEN_CD フォルダに写します。
# GAME1.GOG は読むだけで、書き換えません。
# 使い方: powershell -NoProfile -ExecutionPolicy Bypass -File prepare_cd.ps1 <ゲームのフォルダ>
param([Parameter(Mandatory = $true)][string]$GameDir)
$ErrorActionPreference = 'Stop'

$image = Join-Path $GameDir 'GAME1.GOG'
$outDir = Join-Path $GameDir 'XEEN_CD'
$names = @('XEEN.CC', 'DARK.CC', 'INTRO.CC')

if (-not (Test-Path -LiteralPath $image)) {
    Write-Host "GAME1.GOG が見つかりません: $image"
    exit 1
}

$fs = [System.IO.File]::Open($image, 'Open', 'Read', 'Read')
try {
    # MODE1/2352 の CD イメージ: 1 セクタ 2352 バイトのうち、16 バイト目から 2048 バイトがデータ
    function Read-Data([long]$lba, [long]$size) {
        $buf = New-Object byte[] $size
        $sector = New-Object byte[] 2352
        $done = 0
        while ($done -lt $size) {
            $fs.Position = $lba * 2352
            [void]$fs.Read($sector, 0, 2352)
            $n = [Math]::Min(2048, $size - $done)
            [Array]::Copy($sector, 16, $buf, $done, $n)
            $done += $n
            $lba++
        }
        return , $buf
    }

    # ディレクトリの中身を (名前, 先頭セクタ, 大きさ, ディレクトリか) の一覧にする
    function Read-Dir([long]$lba, [long]$size) {
        $data = Read-Data $lba $size
        $list = @()
        $i = 0
        while ($i -lt $data.Length) {
            $len = $data[$i]
            if ($len -eq 0) { $i = ([Math]::Floor($i / 2048) + 1) * 2048; continue }
            $nameLen = $data[$i + 32]
            $name = [System.Text.Encoding]::ASCII.GetString($data, $i + 33, $nameLen).Split(';')[0]
            $list += [pscustomobject]@{
                Name = $name
                Lba  = [BitConverter]::ToUInt32($data, $i + 2)
                Size = [BitConverter]::ToUInt32($data, $i + 10)
                Dir  = ($data[$i + 25] -band 2) -ne 0
            }
            $i += $len
        }
        return $list
    }

    $pvd = Read-Data 16 2048
    if ([System.Text.Encoding]::ASCII.GetString($pvd, 1, 5) -ne 'CD001') {
        Write-Host 'GAME1.GOG が CD イメージとして読めません。'
        exit 1
    }
    $root = Read-Dir ([BitConverter]::ToUInt32($pvd, 158)) ([BitConverter]::ToUInt32($pvd, 166))
    $game = $root | Where-Object { $_.Dir -and $_.Name -eq 'GAME' } | Select-Object -First 1
    if (-not $game) {
        Write-Host 'GAME1.GOG の中に GAME フォルダが見つかりません。'
        exit 1
    }
    $files = Read-Dir $game.Lba $game.Size

    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    foreach ($n in $names) {
        $f = $files | Where-Object { -not $_.Dir -and $_.Name -eq $n } | Select-Object -First 1
        if (-not $f) {
            Write-Host "GAME1.GOG の中に $n が見つかりません。"
            exit 1
        }
        Write-Host "$n を取り出しています（$([Math]::Round($f.Size / 1MB, 1)) MB）..."
        $bytes = Read-Data $f.Lba $f.Size
        [System.IO.File]::WriteAllBytes((Join-Path $outDir $n), $bytes)
    }
} finally {
    $fs.Close()
}
Write-Host 'CD 版のファイルを XEEN_CD フォルダに用意しました。'
exit 0
