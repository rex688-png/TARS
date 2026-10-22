param([string]$MsiPath, [string]$Version, [string]$OutputPath)
$ErrorActionPreference = 'Stop'

function Assert-MsiRow($Row, [string[]]$Columns, [string]$Query) {
    $type = if ($null -eq $Row) { '<null>' } else { $Row.GetType().FullName }
    if ($Row -isnot [pscustomobject]) { throw "Malformed MSI row ($type) for query: $Query" }
    foreach ($column in $Columns) {
        $property = $Row.PSObject.Properties[$column]
        if ($null -eq $property -or $property.Value -isnot [string]) {
            throw "Malformed MSI row ($type): missing/non-string column '$column'; query: $Query"
        }
    }
}

function Read-MsiRows($Database, [string]$Query, [string[]]$Columns) {
    $view = $Database.OpenView($Query)
    try {
        # COM void methods can return a non-row sentinel through PowerShell.
        [void]$view.Execute()
        while ($null -ne ($record = $view.Fetch())) {
            try {
                if ($record.FieldCount -ne $Columns.Count) { throw "MSI field count $($record.FieldCount) != $($Columns.Count); query: $Query" }
                $row = [ordered]@{}
                for ($i=0; $i -lt $Columns.Count; $i++) { $row[$Columns[$i]] = $record.StringData($i+1) }
                $result = [pscustomobject]$row
                Assert-MsiRow $result $Columns $Query
                $result
            } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($record) }
        }
    } finally {
        [void]$view.Close()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    }
}

function ConvertTo-MsiProperties([object[]]$Rows) {
    $properties = @{}
    foreach ($row in $Rows) {
        Assert-MsiRow $row @('Property','Value') 'Property table'
        if ([string]::IsNullOrWhiteSpace($row.Property)) { throw 'Malformed MSI Property table: empty Property key' }
        if ($properties.ContainsKey($row.Property)) { throw "Malformed MSI Property table: duplicate '$($row.Property)'" }
        $properties[$row.Property] = $row.Value
    }
    foreach ($required in @('ProductVersion','ProductCode','UpgradeCode','ProductName')) {
        if ([string]::IsNullOrWhiteSpace($properties[$required])) { throw "MSI Property table missing required '$required'" }
    }
    return $properties
}

function Get-MsiMetadata([string]$Path) {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.OpenDatabase((Resolve-Path $Path).Path, 0)
    try {
        $properties = ConvertTo-MsiProperties @(Read-MsiRows $database 'SELECT `Property`, `Value` FROM `Property`' @('Property','Value'))
        return [pscustomobject]@{
            ProductVersion=$properties.ProductVersion; ProductCode=$properties.ProductCode
            UpgradeCode=$properties.UpgradeCode; ProductName=$properties.ProductName
            ALLUSERS=$properties.ALLUSERS; MSIINSTALLPERUSER=$properties.MSIINSTALLPERUSER
            Upgrade=@(Read-MsiRows $database 'SELECT `UpgradeCode`, `VersionMin`, `VersionMax`, `Attributes`, `ActionProperty` FROM `Upgrade`' @('UpgradeCode','VersionMin','VersionMax','Attributes','ActionProperty'))
            LaunchCondition=@(Read-MsiRows $database 'SELECT `Condition`, `Description` FROM `LaunchCondition`' @('Condition','Description'))
            InstallExecuteSequence=@(Read-MsiRows $database 'SELECT `Action`, `Sequence` FROM `InstallExecuteSequence`' @('Action','Sequence'))
        }
    } finally {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($database)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer)
    }
}

function Test-MsiMetadata([string]$Path, [string]$SemanticVersion) {
    $expected = & node "$PSScriptRoot/../tools/msi-version.cjs" $SemanticVersion | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Invalid MSI version policy input' }
    $actual = Get-MsiMetadata $Path
    if ($actual.ProductVersion -ne $expected.product_version) { throw "ProductVersion $($actual.ProductVersion) != $($expected.product_version)" }
    if ($actual.UpgradeCode.Trim('{}').ToUpperInvariant() -ne $expected.upgrade_code) { throw 'MSI UpgradeCode continuity failed' }
    if ($actual.ProductName -ne 'TARS' -or $actual.ProductCode -notmatch '^\{[0-9A-F-]{36}\}$') { throw 'Unexpected MSI product identity' }
    $upgrade = @($actual.Upgrade | Where-Object { $_.ActionProperty -eq 'WIX_UPGRADE_DETECTED' })
    $downgrade = @($actual.Upgrade | Where-Object { $_.ActionProperty -eq 'WIX_DOWNGRADE_DETECTED' })
    if ($upgrade.Count -ne 1 -or $upgrade[0].VersionMax -ne $actual.ProductVersion -or -not ([int]$upgrade[0].Attributes -band 512)) { throw 'Same-version major upgrade relationship missing' }
    if ($downgrade.Count -ne 1 -or $downgrade[0].VersionMin -ne $actual.ProductVersion -or -not ([int]$downgrade[0].Attributes -band 2)) { throw 'Downgrade detection relationship missing' }
    if (-not ($actual.LaunchCondition.Condition -match 'WIX_DOWNGRADE_DETECTED')) { throw 'Downgrade launch condition missing' }
    $remove = @($actual.InstallExecuteSequence | Where-Object Action -eq 'RemoveExistingProducts')
    $validate = @($actual.InstallExecuteSequence | Where-Object Action -eq 'InstallValidate')
    $initialize = @($actual.InstallExecuteSequence | Where-Object Action -eq 'InstallInitialize')
    if ($remove.Count -ne 1 -or [int]$remove[0].Sequence -le [int]$validate[0].Sequence -or [int]$remove[0].Sequence -ge [int]$initialize[0].Sequence) { throw 'Expected existing-product removal before new-file installation' }
    return $actual
}

if ($MsiPath) {
    $result = Test-MsiMetadata $MsiPath $Version
    if ($OutputPath) { $result | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $OutputPath }
    Write-Host "::notice title=Actual MSI identity::ProductVersion=$($result.ProductVersion); ProductCode=$($result.ProductCode); UpgradeCode=$($result.UpgradeCode)"
}
