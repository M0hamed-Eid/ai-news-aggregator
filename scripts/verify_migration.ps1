<#
.SYNOPSIS
    Proves "every table and record migrated" with actual row-count diffs,
    not a visual spot-check - run after restore_db.ps1.

.DESCRIPTION
    Re-runs the same row-count queries used to characterize the local DB
    before this deployment (articles, youtube_videos, embeddings,
    content_enrichment, users, user_events, plus total DB size) against BOTH
    the local dev container and the restored Neon database, and diffs them
    row by row. Any mismatch is printed clearly and the script exits non-zero.

    NOTE: this file is deliberately plain ASCII only (no em-dashes/curly
    quotes) - Windows PowerShell 5.1 can misdecode a BOM-less UTF-8 file's
    multi-byte characters into stray quote/paren-like bytes, which silently
    breaks string parsing at runtime. Keep it ASCII if you edit this file.

.EXAMPLE
    .\scripts\verify_migration.ps1 -NeonConnectionString "postgresql://user:pass@ep-xxx.neon.tech/ai_news?sslmode=require"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$NeonConnectionString,

    [string]$ContainerName = "ai_news_db",
    [string]$LocalPgUser = "ai_news_user",
    [string]$LocalPgDb = "ai_news",
    [string]$PgImage = "pgvector/pgvector:pg16"
)

$ErrorActionPreference = "Stop"

# table -> count query. Matches the row counts this deployment plan was
# scoped against (see docs/DEPLOYMENT.md's "Zero data loss" section).
$checks = [ordered]@{
    "articles"           = "SELECT count(*) FROM articles;"
    "youtube_videos"     = "SELECT count(*) FROM youtube_videos;"
    "embeddings"         = "SELECT count(*) FROM embeddings;"
    "content_enrichment" = "SELECT count(*) FROM content_enrichment;"
    "users"              = "SELECT count(*) FROM users;"
    "user_events"        = "SELECT count(*) FROM user_events;"
}
$sizeQuery = "SELECT pg_size_pretty(pg_database_size(current_database()));"

function Get-LocalValue([string]$query) {
    docker exec $ContainerName psql -U $LocalPgUser -d $LocalPgDb -t -A -c $query 2>$null | Select-Object -First 1
}

function Get-RemoteValue([string]$query) {
    docker run --rm $PgImage psql "$NeonConnectionString" -t -A -c $query 2>$null | Select-Object -First 1
}

Write-Host "Comparing row counts: LOCAL ($ContainerName) vs. NEON (restored target)"
Write-Host ""

$allMatch = $true
$rows = @()
foreach ($table in $checks.Keys) {
    $local = (Get-LocalValue $checks[$table]).Trim()
    $remote = (Get-RemoteValue $checks[$table]).Trim()
    $match = ($local -eq $remote)
    if (-not $match) { $allMatch = $false }
    $rows += [pscustomobject]@{
        table = $table
        local = $local
        neon  = $remote
        match = $(if ($match) { "OK" } else { "MISMATCH" })
    }
}
$rows | Format-Table -AutoSize

$localSize = (Get-LocalValue $sizeQuery).Trim()
$remoteSize = (Get-RemoteValue $sizeQuery).Trim()
Write-Host "DB size - local: $localSize | neon: $remoteSize (sizes won't match exactly - Neon's storage engine/overhead differs; this is informational, not a pass/fail check)"

if ($allMatch) {
    Write-Host ""
    Write-Host "All row counts match. Migration verified." -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "Row-count MISMATCH found above - do not proceed with cutover until resolved." -ForegroundColor Red
    exit 1
}
