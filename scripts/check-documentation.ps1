$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$failures = [System.Collections.Generic.List[string]]::new()

$requiredFiles = @(
    "docs/project-status.md",
    "docs/roadmap/README.md",
    "docs/README.md",
    "docs/operations/README.md"
)

foreach ($relativePath in $requiredFiles) {
    $absolutePath = Join-Path $repositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        $failures.Add("Falta el documento obligatorio: $relativePath")
    }
}

$lineLimits = @{
    "docs/project-status.md" = 250
    "docs/roadmap/README.md" = 180
}

foreach ($entry in $lineLimits.GetEnumerator()) {
    $absolutePath = Join-Path $repositoryRoot $entry.Key
    if (Test-Path -LiteralPath $absolutePath -PathType Leaf) {
        $lineCount = (Get-Content -LiteralPath $absolutePath -Encoding utf8).Count
        if ($lineCount -gt $entry.Value) {
            $failures.Add("$($entry.Key) tiene $lineCount lineas; maximo $($entry.Value).")
        }
    }
}

$contractsPath = Join-Path $repositoryRoot "docs/contracts"
Get-ChildItem -LiteralPath $contractsPath -File -Filter "*.md" | ForEach-Object {
    $lineCount = (Get-Content -LiteralPath $_.FullName -Encoding utf8).Count
    if ($lineCount -gt 200) {
        $relativeFile = $_.FullName.Substring($repositoryRoot.Length + 1)
        $failures.Add("$relativeFile tiene $lineCount lineas; un contrato no debe superar 200.")
    }
}

$datedOperations = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot "docs/operations") -File |
    Where-Object { $_.Name -match "-\d{4}-\d{2}-\d{2}\.md$" }
foreach ($file in $datedOperations) {
    $failures.Add("Runbook activo con fecha en el nombre: docs/operations/$($file.Name)")
}

$activeDocumentation = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot "docs") -Recurse -File -Filter "*.md" |
    Where-Object {
        $_.FullName -notmatch "[\\/]docs[\\/]history[\\/]" -and
        $_.Name -ne "evidence-summary.md"
    }
$stalePatterns = @(
    "Estructura futura",
    "Mientras la migracion",
    "al migrar a schema v\d+",
    "Fase \d+ del roadmap",
    "documento principal"
)
foreach ($file in $activeDocumentation) {
    $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8
    foreach ($pattern in $stalePatterns) {
        if ($content -match $pattern) {
            $relativeFile = $file.FullName.Substring($repositoryRoot.Length + 1)
            $failures.Add("Marcador historico en documento activo ${relativeFile}: $pattern")
        }
    }
}

$roadmapPath = Join-Path $repositoryRoot "docs/roadmap/README.md"
if (Test-Path -LiteralPath $roadmapPath -PathType Leaf) {
    $roadmapText = Get-Content -LiteralPath $roadmapPath -Raw -Encoding utf8
    if ($roadmapText -match "(?im)^.*(Estado:\s*\*\*complet|Implementado el|Completado el).*$") {
        $failures.Add("El roadmap contiene cronologia completada; moverla a docs/history/.")
    }
}

$excludedPattern = "[\\/](\.git|\.venv|node_modules)[\\/]"
$markdownFiles = Get-ChildItem -LiteralPath $repositoryRoot -Recurse -File -Filter "*.md" |
    Where-Object { $_.FullName -notmatch $excludedPattern }

foreach ($file in $markdownFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8
    foreach ($match in [regex]::Matches($content, "\[[^\]]*\]\(([^)]+)\)")) {
        $target = $match.Groups[1].Value.Trim()
        if (-not $target -or $target -match "^(https?://|mailto:|#)") {
            continue
        }

        $pathOnly = ($target -replace "^<|>$", "").Split("#")[0]
        if (-not $pathOnly) {
            continue
        }

        $decodedPath = [uri]::UnescapeDataString($pathOnly)
        $candidate = Join-Path $file.DirectoryName $decodedPath
        if (-not (Test-Path -LiteralPath $candidate)) {
            $relativeFile = $file.FullName.Substring($repositoryRoot.Length + 1)
            $failures.Add("Enlace roto en ${relativeFile}: $target")
        }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output "Documentacion valida: archivos obligatorios, limites y enlaces correctos."
