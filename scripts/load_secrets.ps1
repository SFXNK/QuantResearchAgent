# Loads key=value pairs from secrets.properties into the current session's
# environment. Usage:  . .\scripts\load_secrets.ps1
param([string]$Path = "secrets.properties")

if (-not (Test-Path $Path)) {
    Write-Error "secrets file not found: $Path"
    return
}

Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $name = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()
    Set-Item -Path "Env:$name" -Value $value
    Write-Host "loaded $name"
}
