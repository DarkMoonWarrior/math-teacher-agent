$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$examplePath = Join-Path $repositoryRoot ".env.example"
$targetPath = Join-Path $repositoryRoot ".env"

if (-not (Test-Path -LiteralPath $examplePath -PathType Leaf)) {
    throw "Missing environment template: $examplePath"
}

if (Test-Path -LiteralPath $targetPath) {
    throw ".env already exists. Refusing to overwrite local secrets or configuration."
}

$agentServiceToken = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")
$toolGatewayToken = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")
$content = [System.IO.File]::ReadAllText($examplePath)
$content = [System.Text.RegularExpressions.Regex]::Replace(
    $content,
    "(?m)^MATH_AI_AGENT_RUNTIME=.*$",
    "MATH_AI_AGENT_RUNTIME=dsh"
)
$content = [System.Text.RegularExpressions.Regex]::Replace(
    $content,
    "(?m)^MATH_AI_AGENT_SERVICE_TOKEN=.*$",
    "MATH_AI_AGENT_SERVICE_TOKEN=$agentServiceToken"
)
$content = [System.Text.RegularExpressions.Regex]::Replace(
    $content,
    "(?m)^MATH_AI_TOOL_GATEWAY_TOKEN=.*$",
    "MATH_AI_TOOL_GATEWAY_TOKEN=$toolGatewayToken"
)

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($targetPath, $content, $utf8WithoutBom)

Write-Host "Created $targetPath with two distinct local M2M tokens and DSH runtime enabled."
Write-Host "Keep this file private. It is ignored by Git."
