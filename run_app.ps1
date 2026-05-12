$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendPort = 8010
$FrontendPort = 5175
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

function Test-PortOpen {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Get-PortProcessId {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        return $connection.OwningProcess
    }
    return $null
}

function Import-EnvFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return
    }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name -and -not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Write-Host "Starting InvAI Inventory Management System..." -ForegroundColor Cyan

Import-EnvFile (Join-Path $Root ".env")
Import-EnvFile (Join-Path $Backend ".env")

Set-Location $Backend
if ($env:INVENTORY_DATABASE_URL) {
    Write-Host "Database: configured via INVENTORY_DATABASE_URL" -ForegroundColor Cyan
} elseif ($env:MYSQL_USER -and $env:MYSQL_PASSWORD) {
    $mysqlHost = if ($env:MYSQL_HOST) { $env:MYSQL_HOST } else { "127.0.0.1" }
    $mysqlPort = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { "3307" }
    $mysqlDatabase = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "inventory_ai" }
    Write-Host "Database: MySQL via .env ($mysqlHost`:$mysqlPort/$mysqlDatabase)" -ForegroundColor Cyan
} else {
    Write-Host "Database credentials are missing. Set INVENTORY_DATABASE_URL or MYSQL_USER/MYSQL_PASSWORD in .env." -ForegroundColor Yellow
}

$chatProvider = if ($env:AI_CHATBOT_PROVIDER) { $env:AI_CHATBOT_PROVIDER } else { "local fallback" }
$hasGeminiKey = if ($env:GEMINI_API_KEY) { "configured" } else { "missing" }
$hasGrokKey = if ($env:GROK_API_KEY -or $env:XAI_API_KEY) { "configured" } else { "missing" }
Write-Host "AI chatbot provider: $chatProvider (Gemini key: $hasGeminiKey, Grok key: $hasGrokKey)" -ForegroundColor Cyan

if ($env:SEED_DEMO_DATA -eq "1") {
    python seed_demo.py
} else {
    Write-Host "Demo seeding skipped. Set SEED_DEMO_DATA=1 if you want sample records." -ForegroundColor Yellow
}

$backendProcessId = Get-PortProcessId $BackendPort
if ($backendProcessId) {
    $backendProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$backendProcessId"
    if ($backendProcess.CommandLine -like "*uvicorn*api:app*" -or $backendProcess.CommandLine -like "*uvicorn*app.main:app*") {
        Write-Host "Restarting backend on $BackendUrl so it uses the MySQL database..." -ForegroundColor Yellow
        Stop-Process -Id $backendProcessId -Force
        Start-Sleep -Seconds 2
        $backendProcessId = $null
    } else {
        Write-Host "Port $BackendPort is already used by another process. Backend was not restarted." -ForegroundColor Yellow
    }
}

if (-not $backendProcessId) {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$Backend'; python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
    )
    Write-Host "Backend starting on $BackendUrl" -ForegroundColor Green
}

if (Test-PortOpen $FrontendPort) {
    Write-Host "Frontend already running on $FrontendUrl" -ForegroundColor Yellow
} else {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$Frontend'; npm run dev -- --port $FrontendPort"
    )
    Write-Host "Frontend starting on $FrontendUrl" -ForegroundColor Green
}

Start-Sleep -Seconds 5
Start-Process $FrontendUrl

Write-Host ""
Write-Host "InvAI is ready:" -ForegroundColor Cyan
Write-Host "Frontend: $FrontendUrl"
Write-Host "Backend:  $BackendUrl"
