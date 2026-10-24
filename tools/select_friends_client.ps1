$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.OpenFileDialog
$picker.Title = 'Select your existing data\x2_dx11.exe'
$picker.Filter = 'Elsword DX11 (x2_dx11.exe)|x2_dx11.exe'
$picker.CheckFileExists = $true
if ($picker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::WriteLine($picker.FileName)
} else { exit 1 }
