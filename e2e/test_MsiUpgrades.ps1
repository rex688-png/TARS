# Real Windows Installer execution with an inert fixture, on disposable hosted CI only.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:OS -ne 'Windows_NT') { throw 'Disposable GitHub-hosted Windows runner required' }
. "$PSScriptRoot/MsiMetadata.ps1"
$root = Join-Path $env:RUNNER_TEMP 'tars-msi-acceptance'
$matrix = @(Get-Content (Join-Path $root 'matrix.json') -Raw | ConvertFrom-Json)
$metadata = @{}; $steps = [System.Collections.Generic.List[object]]::new()
$installer = New-Object -ComObject WindowsInstaller.Installer
$upgradeCode = '{AC5C2268-982F-5911-BC2F-9D5E9DFDCDF9}'
$syntheticProfile = Join-Path $env:APPDATA 'TARS'
if ((Test-Path $syntheticProfile) -or @($installer.RelatedProducts($upgradeCode)).Count) { throw 'Existing TARS installation/profile detected; refusing acceptance test' }
New-Item -ItemType Directory -Path $syntheticProfile | Out-Null
@{characters=@(@{name='TARS';character='SYNTHETIC PERSONALITY KEEP'});active_character_index=0;plugin_settings=@{synthetic=@{value=42}};tts_provider='synthetic-tts';stt_provider='synthetic-stt';embedding_provider='synthetic-memory'} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $syntheticProfile 'config.json')
Copy-Item (Join-Path $syntheticProfile 'config.json') (Join-Path $syntheticProfile 'config.backup.json')
& python -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("create table acceptance(value text)"); c.execute("insert into acceptance values (?)", ("SYNTHETIC MEMORY KEEP",)); c.commit(); c.close()' (Join-Path $syntheticProfile 'covas.db')
if ($LASTEXITCODE -ne 0) { throw 'Synthetic memory database setup failed' }
New-Item -ItemType Directory (Join-Path $syntheticProfile 'providers/synthetic') -Force | Out-Null
'SYNTHETIC PROVIDER KEEP' | Set-Content (Join-Path $syntheticProfile 'providers/synthetic/marker.txt')
$before = @{}; Get-ChildItem $syntheticProfile -File -Recurse | ForEach-Object { $before[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
function Assert-Profile {
    foreach ($file in $before.Keys) {
        if (-not (Test-Path $file) -or (Get-FileHash $file -Algorithm SHA256).Hash -ne $before[$file]) { throw "Synthetic profile changed: $file" }
    }
}
function Invoke-Msi([string]$Path, [string]$Label) {
    $log = Join-Path $root ($Label+'.log')
    $process = Start-Process msiexec.exe -ArgumentList @('/i',"`"$Path`"",'/qn','/norestart','/l*v',"`"$log`"") -Wait -PassThru
    return [pscustomobject]@{code=$process.ExitCode;log=$log}
}
function Assert-Installed([string]$Code) {
    $related = @($installer.RelatedProducts($upgradeCode))
    if ($related.Count -ne 1 -or $related[0] -ne $Code -or $installer.ProductState($Code) -ne 5) { throw "Expected one installed TARS product $Code; found $related" }
    Assert-Profile
}
try {
    foreach ($item in $matrix) { $metadata[$item.label] = Test-MsiMetadata $item.msi $item.version }
    if (@($metadata.Values.ProductCode | Sort-Object -Unique).Count -ne $matrix.Count) { throw 'Rebuilt MSI ProductCodes must be distinct' }
    $previous = $null
    foreach ($label in @('legacy','beta1','beta2','stable')) {
        $item = $matrix | Where-Object label -eq $label
        $result = Invoke-Msi $item.msi $label
        if ($result.code -notin @(0,3010)) { throw "Install $label failed: $($result.code); $($result.log)" }
        $current = $metadata[$label].ProductCode
        Assert-Installed $current
        if ($previous -and $installer.ProductState($previous) -eq 5) { throw 'Previous product still installed' }
        $steps.Add(@{scenario=$label;exit_code=$result.code;installed=$current;profile_unchanged=$true})
        $previous = $current
    }
    $item = $matrix | Where-Object label -eq 'stable'
    $result = Invoke-Msi $item.msi 'same-package-reinstall'
    if ($result.code -notin @(0,3010)) { throw "Same package reinstall failed: $($result.code)" }
    Assert-Installed $previous
    $steps.Add(@{scenario='same-package-reinstall';exit_code=$result.code;profile_unchanged=$true})
    $item = $matrix | Where-Object label -eq 'stable-rebuilt'
    $result = Invoke-Msi $item.msi 'same-version-rebuilt'
    if ($result.code -notin @(0,3010)) { throw "Same version rebuild failed: $($result.code)" }
    $previous = $metadata['stable-rebuilt'].ProductCode; Assert-Installed $previous
    $steps.Add(@{scenario='same-version-rebuilt';exit_code=$result.code;profile_unchanged=$true})
    $item = $matrix | Where-Object label -eq 'beta2'
    $result = Invoke-Msi $item.msi 'downgrade'
    if ($result.code -eq 0 -or (Get-Content $result.log -Raw) -notmatch 'A newer version of') { throw 'Downgrade was not explicitly rejected' }
    Assert-Installed $previous
    $steps.Add(@{scenario='downgrade-rejected';exit_code=$result.code;profile_unchanged=$true})
    $report = @{metadata=$metadata;scenarios=$steps;profile_hashes_preserved=$true;payload='inert where.exe renamed TARS.exe; no runtime launched'}
    $report | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 (Join-Path $root 'acceptance-report.json')
    Write-Host '::notice title=Real MSI upgrade acceptance::legacy -> beta1 -> beta2 -> stable, identical reinstall, rebuilt same version, downgrade rejection and synthetic profile preservation passed'
} finally {
    foreach ($code in @($installer.RelatedProducts($upgradeCode))) {
        Start-Process msiexec.exe -ArgumentList @('/x',$code,'/qn','/norestart') -Wait | Out-Null
    }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer)
}
