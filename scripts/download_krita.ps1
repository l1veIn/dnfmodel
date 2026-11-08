$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$downloadPath = Join-Path $workspacePath 'tools\downloads\krita-x64-5.3.4.1.zip'
$url = 'https://download.kde.org/stable/krita/5.3.4.1/krita-x64-5.3.4.1.zip'
if (-not (Test-Path -LiteralPath $downloadPath)) {
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $downloadPath -TimeoutSec 240
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($downloadPath)
try {
    if (-not ($zip.Entries | Where-Object { $_.FullName -match '/bin/krita.exe$' })) {
        throw 'The archive does not contain the expected Krita executable.'
    }
    foreach ($entry in $zip.Entries) {
        $resolvedEntry = [System.IO.Path]::GetFullPath((Join-Path (Join-Path $workspacePath 'tools') $entry.FullName))
        if (-not $resolvedEntry.StartsWith((Join-Path $workspacePath 'tools') + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unsafe archive entry path.'
        }
    }
} finally {
    $zip.Dispose()
}
$portablePath = Join-Path $workspacePath 'tools\krita-x64-5.3.4.1'
if (-not (Test-Path -LiteralPath $portablePath)) {
    Expand-Archive -LiteralPath $downloadPath -DestinationPath (Join-Path $workspacePath 'tools')
}
$executablePath = Join-Path $portablePath 'bin\krita.exe'
if (-not (Test-Path -LiteralPath $executablePath)) { throw 'Krita executable not found after extraction.' }
[PSCustomObject]@{
    source = $url
    archive = $downloadPath
    archive_sha256 = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash
    executable = $executablePath
    executable_sha256 = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash
    signature = (Get-AuthenticodeSignature -LiteralPath $executablePath).Status.ToString()
    prepared_at_utc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $workspacePath 'tools\krita_receipt.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $workspacePath 'tools\krita_receipt.json')
