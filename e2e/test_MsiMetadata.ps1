param([switch]$InspectFixture)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/MsiMetadata.ps1"

function Assert-Rejected($Rows, [string]$Expected) {
    try { $null = ConvertTo-MsiProperties $Rows }
    catch {
        if ($_.Exception.Message -notlike "*$Expected*") { throw }
        return
    }
    throw "Expected metadata rejection: $Expected"
}
$valid = @(
    [pscustomobject]@{Property='ProductVersion';Value='0.5.1'},
    [pscustomobject]@{Property='ProductCode';Value='{synthetic}'},
    [pscustomobject]@{Property='UpgradeCode';Value='{synthetic}'},
    [pscustomobject]@{Property='ProductName';Value='TARS'}
)
if ((ConvertTo-MsiProperties $valid).ProductVersion -ne '0.5.1') { throw 'Valid metadata lost' }
Assert-Rejected @($valid + 0) 'System.Int32'
Assert-Rejected @($valid + [DBNull]::Value) 'System.DBNull'
Assert-Rejected @($valid + [pscustomobject]@{Value='missing-key'}) "column 'Property'"
Assert-Rejected @($valid + [pscustomobject]@{Property='';Value='empty-key'}) 'empty Property key'
Assert-Rejected @($valid + $valid[0]) 'duplicate'
Assert-Rejected @($valid[1..3]) "missing required 'ProductVersion'"
Write-Host 'Metadata parsing: valid rows and six malformed/missing-row cases passed'

if ($InspectFixture) {
    $matrix = @(Get-Content (Join-Path $env:RUNNER_TEMP 'tars-msi-acceptance/matrix.json') -Raw | ConvertFrom-Json)
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.OpenDatabase($matrix[0].msi, 0)
    $query = 'SELECT `Property`, `Value` FROM `Property`'
    $view = $database.OpenView($query)
    try {
        # Capture the exact objects formerly emitted into Read-MsiRows' pipeline.
        $executeOutput = @($view.Execute())
        $closeOutput = @($view.Close())
        foreach ($method in @('Execute','Close')) {
            $outputs = if ($method -eq 'Execute') { $executeOutput } else { $closeOutput }
            foreach ($output in $outputs) {
                $type = if ($null -eq $output) { '<null>' } else { $output.GetType().FullName }
                Write-Host "::notice title=MSI COM pipeline diagnosis::$method() returned $type; value='$output'; this is not a Property row"
            }
        }
        $rows = @(Read-MsiRows $database $query @('Property','Value'))
        if ($rows.Count -lt 4) { throw 'MSI Property rows missing' }
        foreach ($row in $rows) { Assert-MsiRow $row @('Property','Value') $query }
        $properties = ConvertTo-MsiProperties $rows
        Write-Host "::notice title=MSI row regression test::$($rows.Count) genuine Property rows; ProductVersion=$($properties.ProductVersion); COM method outputs excluded"
    } finally {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($database)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer)
    }
}
