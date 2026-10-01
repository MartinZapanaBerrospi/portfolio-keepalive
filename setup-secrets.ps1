# Copia las credenciales de los proyectos locales a los GitHub Secrets de este repo.
# Los valores se leen de los .env y se envían directo a `gh secret set`; nunca se imprimen.
# Uso:  .\setup-secrets.ps1

$ErrorActionPreference = "Stop"
$repo = "MartinZapanaBerrospi/portfolio-keepalive"
$base = Split-Path $PSScriptRoot -Parent

function Read-EnvValue($file, $name) {
    $line = Get-Content $file | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -replace "^$name=", "").Trim().Trim('"')
}

$secrets = @{
    DENTAL_SUPABASE_URL        = Read-EnvValue "$base\dental-clinic-web\.env.local" "NEXT_PUBLIC_SUPABASE_URL"
    DENTAL_SUPABASE_ANON_KEY   = Read-EnvValue "$base\dental-clinic-web\.env.local" "NEXT_PUBLIC_SUPABASE_ANON_KEY"
    RISKPREDICTOR_DATABASE_URL = Read-EnvValue "$base\riskpredictor-xai\.env" "DATABASE_URL"
}

foreach ($name in $secrets.Keys) {
    if ($secrets[$name]) {
        # --body evita el salto de línea que PowerShell añade al usar la tubería.
        gh secret set $name --repo $repo --body $secrets[$name]
    } else {
        Write-Warning "$name no encontrado; se omite"
    }
}
