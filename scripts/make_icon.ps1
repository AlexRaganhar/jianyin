# Generates the JianYin application icon (ICO with PNG-compressed frames).
# Requires Windows PowerShell and System.Drawing.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$Root = Split-Path -Parent $PSScriptRoot
$AssetDir = Join-Path $Root "jianyin_app\assets"
New-Item -ItemType Directory -Force $AssetDir | Out-Null

function New-RoundedPath([float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $r * 2
    $path.AddArc($x, $y, $d, $d, 180, 90)
    $path.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $path.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $path.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

function New-IconPng([int]$size) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::Transparent)

    $ink = [System.Drawing.ColorTranslator]::FromHtml("#17202A")
    $paper = [System.Drawing.ColorTranslator]::FromHtml("#FBF8F2")
    $line = [System.Drawing.ColorTranslator]::FromHtml("#D6CEC1")
    $accent = [System.Drawing.ColorTranslator]::FromHtml("#A8443A")
    $accentDeep = [System.Drawing.ColorTranslator]::FromHtml("#7E2F27")
    $muted = [System.Drawing.ColorTranslator]::FromHtml("#7A6B5A")
    $white = [System.Drawing.Color]::White

    $margin = [Math]::Max(1, [int]($size * 0.035))
    $bg = New-RoundedPath $margin $margin ($size - 2 * $margin) ($size - 2 * $margin) ($size * 0.19)
    $brush = New-Object System.Drawing.SolidBrush($ink)
    $g.FillPath($brush, $bg)
    $brush.Dispose()
    $bg.Dispose()

    $px = $size * 0.13
    $py = $size * 0.105
    $pw = $size * 0.74
    $ph = $size * 0.79
    $paperPath = New-RoundedPath $px $py $pw $ph ($size * 0.045)
    $brush = New-Object System.Drawing.SolidBrush($paper)
    $g.FillPath($brush, $paperPath)
    $brush.Dispose()
    $pen = New-Object System.Drawing.Pen($line, [Math]::Max(1, $size * 0.008))
    $g.DrawPath($pen, $paperPath)
    $pen.Dispose()
    $paperPath.Dispose()

    if ($size -ge 32) {
        $pen = New-Object System.Drawing.Pen($muted, [Math]::Max(1, $size * 0.025))
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $x1 = $size * 0.23
        $x2 = $size * 0.58
        foreach ($yf in @(0.29, 0.385, 0.48)) {
            $g.DrawLine($pen, $x1, $size * $yf, $x2, $size * $yf)
        }
        $pen.Dispose()
        $barBrush = New-Object System.Drawing.SolidBrush($ink)
        $barPath = New-RoundedPath ($size * 0.23) ($size * 0.37) ($size * 0.34) ($size * 0.03) ($size * 0.015)
        $g.FillPath($barBrush, $barPath)
        $barPath.Dispose()
        $barBrush.Dispose()
    }
    elseif ($size -ge 16) {
        $pen = New-Object System.Drawing.Pen($muted, [Math]::Max(1, $size * 0.04))
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($pen, $size * 0.23, $size * 0.30, $size * 0.53, $size * 0.30)
        $g.DrawLine($pen, $size * 0.23, $size * 0.42, $size * 0.53, $size * 0.42)
        $pen.Dispose()
    }

    $sx = $size * 0.58
    $sy = $size * 0.57
    $sw = $size * 0.27
    $sh = $size * 0.27
    $seal = New-RoundedPath $sx $sy $sw $sh ($size * 0.025)
    $brush = New-Object System.Drawing.SolidBrush($accent)
    $g.FillPath($brush, $seal)
    $brush.Dispose()
    $pen = New-Object System.Drawing.Pen($accentDeep, [Math]::Max(1, $size * 0.01))
    $g.DrawPath($pen, $seal)
    $pen.Dispose()
    $seal.Dispose()

    if ($size -ge 48) {
        $fontSize = [Math]::Max(6, $size * 0.17)
        $font = New-Object System.Drawing.Font("Microsoft YaHei UI", $fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $format = New-Object System.Drawing.StringFormat
        $format.Alignment = [System.Drawing.StringAlignment]::Center
        $format.LineAlignment = [System.Drawing.StringAlignment]::Center
        $brush = New-Object System.Drawing.SolidBrush($white)
        $rect = New-Object System.Drawing.RectangleF($sx, $sy, $sw, $sh)
        $g.DrawString("笺", $font, $brush, $rect, $format)
        $brush.Dispose()
        $format.Dispose()
        $font.Dispose()
    }
    elseif ($size -ge 16) {
        $brush = New-Object System.Drawing.SolidBrush($white)
        $bar = New-RoundedPath ($sx + $sw * 0.28) ($sy + $sh * 0.44) ($sw * 0.44) ([Math]::Max(1, $size * 0.055)) ([Math]::Max(1, $size * 0.02))
        $g.FillPath($brush, $bar)
        $bar.Dispose()
        $brush.Dispose()
    }

    $stream = New-Object System.IO.MemoryStream
    $bmp.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $stream.ToArray()
    $stream.Dispose()
    $g.Dispose()
    $bmp.Dispose()
    return ,$bytes
}

$sizes = @(16, 24, 32, 48, 64, 128, 256)
$images = @()
foreach ($size in $sizes) {
    $images += ,(New-IconPng $size)
    if ($size -eq 256) {
        [System.IO.File]::WriteAllBytes((Join-Path $AssetDir "jianyin.png"), $images[-1])
    }
}

$headerSize = 6 + 16 * $images.Count
$offset = $headerSize
$stream = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($stream)
$writer.Write([UInt16]0)
$writer.Write([UInt16]1)
$writer.Write([UInt16]$images.Count)
for ($i = 0; $i -lt $images.Count; $i++) {
    $size = $sizes[$i]
    $writer.Write([Byte]$(if ($size -ge 256) { 0 } else { $size }))
    $writer.Write([Byte]$(if ($size -ge 256) { 0 } else { $size }))
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$images[$i].Length)
    $writer.Write([UInt32]$offset)
    $offset += $images[$i].Length
}
foreach ($image in $images) {
    $writer.Write([Byte[]]$image)
}
$writer.Flush()
[System.IO.File]::WriteAllBytes((Join-Path $AssetDir "jianyin.ico"), $stream.ToArray())
$writer.Dispose()
$stream.Dispose()
Write-Host "Icon written to $AssetDir"
