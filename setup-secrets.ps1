# Copia las credenciales de los proyectos locales a los GitHub Secrets de este repo.
# Los valores se leen de los .env y se envían directo a `gh secret set`; nunca se imprimen.
# Uso:  .\setup-secrets.ps1
#
# Para un proyecto Supabase nuevo: añade aquí su <PROYECTO>_DATABASE_URL (cadena del
# "Session pooler", puerto 5432) y regístralo en targets.json y en keepalive.yml.

$ErrorActionPreference = "Stop"
$repo = "MartinZapanaBerrospi/portfolio-keepalive"
$base = Split-Path $PSScriptRoot -Parent

function Read-EnvValue($file, $name) {
    if (-not (Test-Path $file)) { return $null }
    $line = Get-Content $file | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -replace "^$name=", "").Trim().Trim('"')
}

# Cadena del Session pooler de Supabase (IPv4: los runners de GitHub no tienen IPv6,
# así que la conexión directa db.<ref>.supabase.co no funciona desde Actions).
function New-PoolerDsn($ref, $host_, $password) {
    if (-not $password) { return $null }
    $pw = [uri]::EscapeDataString($password)
    return "postgresql://postgres.${ref}:${pw}@${host_}:5432/postgres?sslmode=require"
}

$dental = "$base\dental-clinic-web\.env.local"
$entrenador = "$base\entrenador-admision\apps\web\.env.local"

$secrets = [ordered]@{
    DENTAL_SUPABASE_URL            = Read-EnvValue $dental "NEXT_PUBLIC_SUPABASE_URL"
    DENTAL_SUPABASE_ANON_KEY       = Read-EnvValue $dental "NEXT_PUBLIC_SUPABASE_ANON_KEY"
    DENTAL_DATABASE_URL            = New-PoolerDsn "shvoabiqobhdrptuftib" "aws-1-us-east-1.pooler.supabase.com" (Read-EnvValue $dental "SUPABASE_DB_PASSWORD")
    RISKPREDICTOR_DATABASE_URL     = Read-EnvValue "$base\riskpredictor-xai\.env" "DATABASE_URL"
    ENTRENADOR_SUPABASE_URL        = Read-EnvValue $entrenador "NEXT_PUBLIC_SUPABASE_URL"
    ENTRENADOR_SUPABASE_SECRET_KEY = Read-EnvValue $entrenador "SUPABASE_SECRET_KEY"
    # No está en el .env por defecto: añade SUPABASE_DB_URL=<cadena Session pooler> a ese .env.local
    ENTRENADOR_DATABASE_URL        = Read-EnvValue $entrenador "SUPABASE_DB_URL"
}

foreach ($name in $secrets.Keys) {
    if ($secrets[$name]) {
        # --body evita el salto de línea que PowerShell añade al usar la tubería.
        gh secret set $name --repo $repo --body $secrets[$name]
    } else {
        Write-Warning "$name no encontrado; se omite"
    }
}
