<#
.SYNOPSIS
  Validate DAX measures in the open Power BI Desktop model against Python-computed expected values.
.DESCRIPTION
  1. Finds the local Analysis Services port of the running Power BI Desktop instance
     (or uses -Port).
  2. For each row of data/curated/dax_expected_values.csv evaluates the measure under the
     stated filter context with ADOMD.NET and compares to the expected value
     (relative tolerance 1e-9; counts must match exactly).
  3. Evaluates every model measure at the grand total to catch DAX errors.
  4. Compares row counts of every table with its source CSV.
  Writes data/curated/dax_validation_results.csv and prints a summary. Exit code 1 on any failure.
.NOTES
  Requires Power BI Desktop to be open on "HDB Resale Market.pbip" with data refreshed.
#>
param([int]$Port = 0, [string]$PbiBin = 'C:\Program Files\Microsoft Power BI Desktop\bin')
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$curated = Join-Path $repo 'data\curated'
if ($Port -eq 0) {
  $f = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces" -Recurse -Filter 'msmdsrv.port.txt' |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $Port = [int]([System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::Unicode).Trim())
}
[void][System.Reflection.Assembly]::LoadFrom((Join-Path $PbiBin 'Microsoft.PowerBI.AdomdClient.dll'))
[void][System.Reflection.Assembly]::LoadFrom((Join-Path $PbiBin 'Microsoft.PowerBI.Tabular.dll'))
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$conn.Open()
function Eval([string]$dax) {
  $cmd = $conn.CreateCommand(); $cmd.CommandText = $dax
  $r = $cmd.ExecuteReader(); [void]$r.Read(); $v = $r.GetValue(0); $r.Close(); return $v
}
$filters = @{ 'no filter' = ''; 'town=BEDOK, flat_type=4 ROOM' = ', dim_town[town] = "BEDOK", dim_flat_type[flat_type] = "4 ROOM"' }
$results = @(); $fail = 0
foreach ($row in (Import-Csv (Join-Path $curated 'dax_expected_values.csv'))) {
  $dax = "EVALUATE ROW(""v"", CALCULATE([$($row.measure)]$($filters[$row.filter_context])))"
  $actual = [double](Eval $dax); $exp = [double]$row.expected_value
  $ok = [math]::Abs($actual - $exp) -le [math]::Max(1e-9 * [math]::Abs($exp), 1e-9)
  if (-not $ok) { $fail++ }
  $results += [pscustomobject]@{ check = 'measure vs python'; measure = $row.measure; filter_context = $row.filter_context;
                                 expected = $exp; actual = $actual; pass = $ok }
}
# All measures evaluate without error at grand total
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$Port")
$model = $srv.Databases[0].Model
foreach ($t in $model.Tables) {
  foreach ($m in $t.Measures) {
    try { $v = Eval "EVALUATE ROW(""v"", [$($m.Name)])"; $ok = $true; $msg = "$v" } catch { $ok = $false; $msg = $_.Exception.GetBaseException().Message; $fail++ }
    $results += [pscustomobject]@{ check = 'measure evaluates'; measure = $m.Name; filter_context = 'grand total'; expected = ''; actual = $msg; pass = $ok }
  }
  $n = [int64](Eval "EVALUATE ROW(""n"", COUNTROWS('$($t.Name)'))")
  $csv = Join-Path $curated ($t.Partitions[0].Source.Expression | Select-String -Pattern '"([a-z_0-9]+\.csv)"').Matches[0].Groups[1].Value
  $csvRows = 0; $sr = New-Object System.IO.StreamReader($csv); [void]$sr.ReadLine()
  while ($null -ne $sr.ReadLine()) { $csvRows++ }; $sr.Close()
  $ok = ($n -eq $csvRows); if (-not $ok) { $fail++ }
  $results += [pscustomobject]@{ check = 'row count vs csv'; measure = $t.Name; filter_context = ''; expected = $csvRows; actual = $n; pass = $ok }
}
$srv.Disconnect(); $conn.Close()
$results | Export-Csv (Join-Path $curated 'dax_validation_results.csv') -NoTypeInformation -Encoding UTF8
$results | Group-Object check | ForEach-Object { "{0}: {1} checks, {2} passed" -f $_.Name, $_.Count, @($_.Group | ? pass).Count }
if ($fail -gt 0) { "FAILURES:"; $results | ? { -not $_.pass } | Format-Table -AutoSize | Out-String -Width 250; exit 1 } else { "ALL CHECKS PASSED" }
