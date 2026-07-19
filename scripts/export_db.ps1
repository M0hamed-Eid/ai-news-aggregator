<#
.SYNOPSIS
    Exports the LOCAL dev Postgres (docker/docker-compose.yml's `db` service)
    to a single custom-format dump file, ready for scripts/restore_db.ps1.

.DESCRIPTION
    Uses `pg_dump -Fc` (custom format) INSIDE the running `ai_news_db`
    container - no local Postgres client install required. Custom format is
    compressed and lets pg_restore recreate schema+data+indexes+constraints
    in one shot, which is what restore_db.ps1 relies on.

    NOTE: this file is deliberately plain ASCII only (no em-dashes/curly
    quotes) - Windows PowerShell 5.1 can misdecode a BOM-less UTF-8 file's
    multi-byte characters into stray quote/paren-like bytes, which silently
    breaks string parsing at runtime. Keep it ASCII if you edit this file.

.EXAMPLE
    .\scripts\export_db.ps1
    .\scripts\export_db.ps1 -OutFile .\backups\ai_news_2026-07-19.dump
#>
param(
    [string]$ContainerName = "ai_news_db",
    [string]$PgUser = "ai_news_user",
    [string]$PgDb = "ai_news",
    [string]$OutFile = ".\ai_news_export.dump"
)

$ErrorActionPreference = "Stop"

$running = docker ps --filter "name=$ContainerName" --format "{{.Names}}"
if (-not $running) {
    throw "Container '$ContainerName' is not running. Start it first: docker compose -f docker/docker-compose.yml up -d db"
}

Write-Host "Dumping $PgDb from $ContainerName (custom format)..."
docker exec $ContainerName pg_dump -U $PgUser -d $PgDb -Fc -f /tmp/ai_news_export.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed (exit $LASTEXITCODE)" }

Write-Host "Copying dump out of the container to $OutFile ..."
docker cp "${ContainerName}:/tmp/ai_news_export.dump" $OutFile
if ($LASTEXITCODE -ne 0) { throw "docker cp failed (exit $LASTEXITCODE)" }

docker exec $ContainerName rm -f /tmp/ai_news_export.dump

$size = (Get-Item $OutFile).Length
Write-Host "Done: $OutFile ($([math]::Round($size/1MB, 2)) MB)"
Write-Host "Next: .\scripts\restore_db.ps1 -NeonConnectionString '<postgres://...>' -DumpFile '$OutFile'"
