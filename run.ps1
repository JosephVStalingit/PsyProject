# ============================================================================
#  run.ps1  --  Unified entry point for the config-driven spring-magnet FEM
#              project.  Driven by config.json (multiple runs).
#
#  Usage:
#    .\run.ps1              # run all runs in config.json
#    .\run.ps1 run1,run2    # run only the named runs
#    .\run.ps1 scope        # same as default (alias)
#    .\run.ps1 clean        # remove intermediate artifacts
#    .\run.ps1 help         # show this message
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Info($msg) { Write-Host (C "1;34" " info  ") -NoNewline; Write-Host " $msg" }
function Ok($msg)   { Write-Host (C "1;32" "  ok   ") -NoNewline; Write-Host " $msg" }
function Warn($msg) { Write-Host (C "1;33" " warn  ") -NoNewline; Write-Host " $msg" }
function Err($msg)  { Write-Host (C "1;31" "  err  ") -NoNewline; Write-Host " $msg" }
function Step($n, $msg) { Write-Host (C "1;36" "[$n/3] ") -NoNewline; Write-Host $msg }
function C([string]$c, [string]$s) {
    if ($Host.UI.SupportsVirtualTerminal) { return "`e[$c$s`e[0m" }
    return $s
}

function Show-Help {
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [TARGET]"
    Write-Host ""
    Write-Host "Targets:"
    Write-Host "  (default)  -- run all runs defined in config.json"
    Write-Host "  scope      -- alias for default"
    Write-Host "  RUNS       -- comma-separated run names (subset of config.json)"
    Write-Host "  clean      -- remove results/ and __pycache__"
    Write-Host "  help       -- this message"
    Write-Host ""
    Write-Host "Files:"
    Write-Host "  config.json     -- multi-run config (see --write-default-config)"
    Write-Host "  simulate.py     -- main simulator (driven by config.json)"
    Write-Host "  results/        -- outputs (dashboard.png, summary.txt, data.json)"
    Write-Host ""
}

# ----------------------------------------------------------------------------
# Locate Python
# ----------------------------------------------------------------------------
function Find-Python {
    foreach ($cand in @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Users\JosephVStalin\AppData\Local\Programs\Python\Python311\python.exe",
        "C:\Python314\python.exe",
        "python"
    )) {
        $p = Get-Command $cand -ErrorAction SilentlyContinue
        if ($p) { return $p.Source }
    }
    return $null
}

$PY = Find-Python
if (-not $PY) {
    Err "python not found - install Python 3.11+ and pip install gmsh meshio pyvista"
    exit 1
}
Info "PY=$PY"

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
function Run-Exe {
    param(
        [Parameter(Mandatory=$true)][string]$Exe,
        [Parameter(Mandatory=$true)][string[]]$Args,
        [string]$LogFile = $null
    )
    $quoted = foreach ($a in $Args) {
        if ($a -match ' ') { '"' + $a + '"' } else { $a }
    }
    $proc = Start-Process -FilePath $Exe -ArgumentList ($quoted -join ' ') `
        -NoNewWindow -PassThru -Wait
    if ($LogFile) {
        Set-Content -Path $LogFile -Value "Run-Exe: $Exe $($quoted -join ' ')\nexit=$($proc.ExitCode)" -Encoding UTF8
    }
    return $proc.ExitCode
}

function Invoke-Clean {
    Info "cleaning intermediate artifacts ..."
    $dirs = @("results", "__pycache__")
    foreach ($d in $dirs) {
        if (Test-Path $d) {
            $size = (Get-ChildItem $d -Recurse -ErrorAction SilentlyContinue |
                     Measure-Object Length -Sum).Sum
            Remove-Item -Recurse -Force $d
            Write-Host ("  removed  {0,-12} {1,10:N1} kB" -f $d, ($size/1KB))
        }
    }
    $current = (Get-ChildItem -File | Measure-Object Length -Sum).Sum
    Write-Host ("  current project size: {0:N1} kB" -f ($current/1KB))
}

function Invoke-Simulate {
    param([string]$RunList = "")
    if (-not (Test-Path config.json)) {
        Err "config.json not found"
        Write-Host "  create one with: python simulate.py --write-default"
        return $false
    }
    New-Item -ItemType Directory -Force -Path results | Out-Null
    $args = @("simulate.py")
    if ($RunList) { $args += @("--runs", $RunList) }
    $rc = Run-Exe -Exe $PY -Args $args
    if ($rc -ne 0) { Err "simulate.py failed (exit=$rc)"; return $false }
    if (Test-Path results/dashboard.png) {
        Ok ("dashboard.png  ({0:N1} kB)" -f ([double](Get-Item results/dashboard.png).Length/1KB))
    }
    if (Test-Path results/summary.txt) { Ok "summary.txt" }
    if (Test-Path results/data.json)   { Ok "data.json" }
    return $true
}

# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------
$target = if ($args.Count -gt 0) { $args[0] } else { "default" }

switch ($target) {
    "help"   { Show-Help }
    "clean"  { Invoke-Clean }
    "scope"  {
        Step 1 "running all config.json runs through simulate.py"
        Invoke-Simulate
    }
    "default" {
        Step 1 "running all config.json runs through simulate.py"
        Invoke-Simulate
    }
    default {
        # Treat the argument as a comma-separated run list.
        $runs = $target -replace '\s+', ''
        if ($runs -match '^[A-Za-z0-9_,\-]+$') {
            Step 1 "running runs: $runs"
            Invoke-Simulate -RunList $runs
        } else {
            Err "unknown target: $target"
            Show-Help
        }
    }
}

Write-Host ""
Ok "done"
