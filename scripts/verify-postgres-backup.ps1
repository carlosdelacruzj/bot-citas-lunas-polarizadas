param(
    [string]$Container = "appointment-bot-postgres"
)

$ErrorActionPreference = "Stop"
$Suffix = Get-Date -Format "yyyyMMddHHmmss"
$DumpPath = "/tmp/appointment-bot-verify-$Suffix.dump"
$VerifyDatabase = "appointment_bot_verify_$Suffix"

function Invoke-PostgresCommand {
    param([string[]]$Arguments)
    & docker exec $Container @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker exec failed: $($Arguments -join ' ')"
    }
}

$User = (& docker exec $Container printenv POSTGRES_USER).Trim()
$Database = (& docker exec $Container printenv POSTGRES_DB).Trim()
if (-not $User -or -not $Database) {
    throw "Could not read POSTGRES_USER and POSTGRES_DB from $Container."
}

try {
    Invoke-PostgresCommand @("pg_dump", "-U", $User, "-d", $Database, "-Fc", "-f", $DumpPath)
    Invoke-PostgresCommand @("createdb", "-U", $User, $VerifyDatabase)
    Invoke-PostgresCommand @("pg_restore", "-U", $User, "-d", $VerifyDatabase, "--no-owner", $DumpPath)

    $Tables = @("service_orders", "runs", "reservations", "reservation_attempts", "payments")
    foreach ($Table in $Tables) {
        $SourceCount = (& docker exec $Container psql -U $User -d $Database -Atc "SELECT COUNT(*) FROM $Table;").Trim()
        $RestoredCount = (& docker exec $Container psql -U $User -d $VerifyDatabase -Atc "SELECT COUNT(*) FROM $Table;").Trim()
        if ($SourceCount -ne $RestoredCount) {
            throw "Row count mismatch for ${Table}: source=$SourceCount restored=$RestoredCount"
        }
        Write-Host "$Table verified: $SourceCount rows"
    }
    Write-Host "Backup and restore verification completed without keeping a dump."
} finally {
    & docker exec $Container dropdb -U $User --if-exists $VerifyDatabase 2>$null
    & docker exec $Container rm -f $DumpPath 2>$null
}
