<#
.SYNOPSIS
    Restores a dump produced by export_db.ps1 into a Neon (or any remote)
    Postgres database, creating the pgvector extension first.

.DESCRIPTION
    Runs psql/pg_restore from a throwaway `pgvector/pgvector:pg16` container
    (same major version as the local dev image) so no local Postgres client
    install is required - only Docker itself, network egress to Neon.

    Step 1: CREATE EXTENSION IF NOT EXISTS vector - Neon's database starts
    empty; locally this extension is created by this project's own Alembic
    migration (alembic/versions/..._add_content_intelligence_layer_tables.py
    and friends), which never runs against a brand-new Neon database. Without
    this, pg_restore fails the moment it hits any vector-typed column.
    Step 2: pg_restore --no-owner --no-privileges - the dump's role names
    (ai_news_user) won't exist on Neon; these flags make ownership/grants
    resolve to whichever role the connection string authenticates as instead
    of failing on unknown roles.

    NOTE: this file is deliberately plain ASCII only (no em-dashes/curly
    quotes) - Windows PowerShell 5.1 can misdecode a BOM-less UTF-8 file's
    multi-byte characters into stray quote/paren-like bytes, which silently
    breaks string parsing at runtime. Keep it ASCII if you edit this file.

.EXAMPLE
    .\scripts\restore_db.ps1 -NeonConnectionString "postgresql://user:pass@ep-xxx.neon.tech/ai_news?sslmode=require" -DumpFile .\ai_news_export.dump
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$NeonConnectionString,

    [string]$DumpFile = ".\ai_news_export.dump",

    [string]$PgImage = "pgvector/pgvector:pg16"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DumpFile)) {
    throw "Dump file not found: $DumpFile - run .\scripts\export_db.ps1 first."
}

$dumpFull = (Resolve-Path $DumpFile).Path
$dumpDir = Split-Path $dumpFull -Parent
$dumpName = Split-Path $dumpFull -Leaf

Write-Host "Creating the pgvector extension on the target database (safe if it already exists)..."
docker run --rm -v "${dumpDir}:/dump" $PgImage psql "$NeonConnectionString" -c "CREATE EXTENSION IF NOT EXISTS vector;"
if ($LASTEXITCODE -ne 0) { throw "CREATE EXTENSION failed (exit $LASTEXITCODE) - check the connection string." }

Write-Host "Restoring $DumpFile into the target database..."
docker run --rm -v "${dumpDir}:/dump" $PgImage pg_restore --no-owner --no-privileges --clean --if-exists -d "$NeonConnectionString" "/dump/$dumpName"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pg_restore exited non-zero ($LASTEXITCODE). pg_restore commonly reports warnings for harmless things (e.g. 'role does not exist' from --no-owner edge cases) - check the output above for ACTUAL errors before assuming this failed. Next: .\scripts\verify_migration.ps1 to confirm row counts regardless."
} else {
    Write-Host "Restore completed cleanly."
}

Write-Host "Next: .\scripts\verify_migration.ps1 -NeonConnectionString '<same string>' to confirm every table/record migrated."
