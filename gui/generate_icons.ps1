Add-Type -AssemblyName System.Drawing

$bmp = New-Object System.Drawing.Bitmap 32, 32
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 59, 130, 246))

$icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
$stream = [System.IO.File]::Create('gui/src-tauri/icons/icon.ico')
$icon.Save($stream)
$stream.Close()

$bmp.Save('gui/src-tauri/icons/32x32.png', [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Save('gui/src-tauri/icons/128x128.png', [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
$g.Dispose()

Write-Host "Icons generated successfully!"
