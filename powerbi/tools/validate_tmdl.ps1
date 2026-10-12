<#
.SYNOPSIS
  Parse the PBIP semantic model with Power BI Desktop's own TMDL serializer (offline syntax/reference check).
.DESCRIPTION
  Loads Microsoft.PowerBI.Tabular.dll from the local Power BI Desktop install and calls
  TmdlSerializer.DeserializeDatabaseFromFolder. Any syntax error, unknown property or broken
  reference (e.g. a relationship to a missing column) throws. Prints a summary on success.
  This does NOT evaluate DAX or load data; see query_model.ps1 for that.
#>
param(
  [string]$ModelFolder = (Join-Path $PSScriptRoot '..\HDB Resale Market.SemanticModel\definition'),
  [string]$PbiBin = 'C:\Program Files\Microsoft Power BI Desktop\bin'
)
$ErrorActionPreference = 'Stop'
[void][System.Reflection.Assembly]::LoadFrom((Join-Path $PbiBin 'Microsoft.PowerBI.Tabular.dll'))
try {
  $db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder((Resolve-Path $ModelFolder).Path)
} catch {
  Write-Output "TMDL VALIDATION FAILED: $($_.Exception.GetBaseException().Message)"
  exit 1
}
$m = $db.Model
$measures = ($m.Tables | ForEach-Object { $_.Measures.Count } | Measure-Object -Sum).Sum
Write-Output ("TMDL OK: compatibilityLevel={0}; tables={1}; columns={2}; measures={3}; relationships={4}; expressions={5}" -f `
  $db.CompatibilityLevel, $m.Tables.Count, ($m.Tables | ForEach-Object { $_.Columns.Count } | Measure-Object -Sum).Sum, `
  $measures, $m.Relationships.Count, $m.Expressions.Count)
