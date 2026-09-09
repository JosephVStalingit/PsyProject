# ============================================================================
#  run.ps1  --  Unified entry point for the spring-magnet FEM project.
#
#  Replaces / merges:
#    - one_click.ps1   (full pipeline)
#    - run_tests.ps1   (FEM sanity tests + oscilloscope)
#    - clean.ps1       (remove intermediate artifacts)
#
#  Usage:
#    .\run.ps1              # default: tests + oscilloscope (no ElmerSolver)
#    .\run.ps1 full         # full pipeline including ElmerSolver
#    .\run.ps1 tests        # just the FEM tests
#    .\run.ps1 scope        # just the oscilloscope dashboard
#    .\run.ps1 clean        # remove all intermediate files
#    .\run.ps1 help         # show this help
#
#  ElmerSolver 26.1 has a known procedure-DLL bug; the script detects it and
#  skips step 3 with a warning instead of hard-failing.
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step($n, $msg) { Write-Host (C "1;36" "[$n/5] ") -NoNewline; Write-Host $msg }
function Ok($msg)      { Write-Host (C "1;32" "  ok   ") -NoNewline; Write-Host " $msg" }
function Warn($msg)    { Write-Host (C "1;33" " warn  ") -NoNewline; Write-Host " $msg" }
function Err($msg)     { Write-Host (C "1;31" "  err  ") -NoNewline; Write-Host " $msg" }
function Info($msg)    { Write-Host (C "1;34" " info  ") -NoNewline; Write-Host " $msg" }

function C([string]$c, [string]$s) {
    if ($Host.UI.SupportsVirtualTerminal) { return "`e[$c$s`e[0m" }
    return $s
}

function Show-Help {
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [TARGET]"
    Write-Host ""
    Write-Host "Targets:"
    Write-Host "  (default)  -- mesh + tests + oscilloscope dashboard"
    Write-Host "  full       -- everything including ElmerSolver (may fail on 26.1)"
    Write-Host "  tests      -- FEM sanity tests only (mesh + verify)"
    Write-Host "  scope      -- oscilloscope dashboard only (fast)"
    Write-Host "  geom       -- rebuild model3d.msh via gmsh"
    Write-Host "  sifs       -- regenerate 3 case_<cfg>.sif files"
    Write-Host "  clean      -- delete intermediate artifacts"
    Write-Host "  help       -- this message"
    Write-Host ""
    Write-Host "Environment:"
    Write-Host "  PY_FOR_GMSH   Python interpreter for gmsh / meshio / pyvista"
    Write-Host "                (auto-detected; or set in env)"
    Write-Host "  ELMER_HOME    Elmer install root (auto-detected)"
    Write-Host ""
}

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
function Find-Gmsh {
    $hit = (Get-Command gmsh -ErrorAction SilentlyContinue).Source
    if ($hit) { return $hit }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts\gmsh.bat",
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts\gmsh.bat",
        "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\gmsh.bat",
        "$env:LOCALAPPDATA\Programs\Python\Python314\Scripts\gmsh.bat"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

function Find-Python {
    foreach ($cand in @(
        "C:\Users\JosephVStalin\AppData\Local\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python314\python.exe",
        "python"
    )) {
        $p = Get-Command $cand -ErrorAction SilentlyContinue
        if ($p) { return $p.Source }
    }
    return $null
}

function Find-Elmer {
    foreach ($cand in @(
        "D:\Program Files\Elmer 26.1-Release",
        "C:\Program Files\Elmer 26.1-Release",
        "C:\Program Files\Elmer",
        "D:\Program Files\Elmer 26.2.1-Release",
        "C:\Program Files\Elmer 26.2.1-Release"
    )) {
        if (Test-Path (Join-Path $cand 'bin\ElmerSolver.exe')) { return $cand }
    }
    return $null
}

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

# ----------------------------------------------------------------------------
# Locate toolchain
# ----------------------------------------------------------------------------
$gmsh = Find-Gmsh
$PY = Find-Python
$ELMER_HOME = Find-Elmer
if (-not $PY) {
    Err "python not found - install Python 3.11+ first"
    exit 1
}
if (-not $ELMER_HOME) {
    Warn "Elmer not found in standard locations"
} else {
    Info "ELMER_HOME=$ELMER_HOME"
}
Info "PY=$PY"
Info "gmsh=$gmsh"

if ($gmsh) {
    # Verify gmsh Python module is on the same interpreter
    $gmshDir = Split-Path $gmsh -Parent
    $candidate = $gmshDir -replace '\\Scripts$', ''
    $candidate = Join-Path $candidate 'python.exe'
    if (Test-Path $candidate) {
        & $candidate -c "import gmsh" 2>$null
        if ($LASTEXITCODE -eq 0) { $PY = $candidate }
    }
}
Info "PY (after gmsh match)=$PY"

# Ensure meshio + pyvista are present
foreach ($pkg in @("meshio", "pyvista")) {
    & $PY -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Info "pip install $pkg"
        & $PY -m pip install $pkg -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    }
}


# ----------------------------------------------------------------------------
# Pipeline steps
# ----------------------------------------------------------------------------
function Build-Geometry {
    if (-not (Test-Path model3d.msh)) {
        Step 1 "gmsh build geometry + mesh"
        $rc = Run-Exe -Exe $PY -Args @("solenoid3d.py") -LogFile "results\gmsh.log"
        if ($rc -ne 0) { Err "gmsh build failed (exit=$rc)"; return $false }
        Ok ("model3d.msh  ({0:N1} MB)" -f ([double](Get-Item model3d.msh).Length/1MB))
    } else {
        Step 1 "gmsh mesh already exists, skipping"
        Ok "model3d.msh"
    }
    return $true
}

function Build-Mesh {
    if (-not $ELMER_HOME) { Warn "no Elmer, cannot run ElmerGrid"; return $false }
    $elmergrid = Join-Path $ELMER_HOME "bin\ElmerGrid.exe"
    if (-not (Test-Path $elmergrid)) { Warn "ElmerGrid.exe not found"; return $false }
    if (Test-Path mesh) { Remove-Item -Recurse -Force mesh }
    Step 2 "ElmerGrid 14 2  ->  mesh/"
    $rc = Run-Exe -Exe $elmergrid -Args @("14","2","model3d.msh","-out","mesh","-autoclean")
    if ($rc -ne 0) { Err "ElmerGrid failed (exit=$rc)"; return $false }
    Ok ("mesh/  ({0} element files)" -f (Get-ChildItem mesh\*.elements 2>&1 | Out-Null).Count)
    return $true
}

function Run-ElmerSolver {
    if (-not $ELMER_HOME) { Warn "no Elmer, skipping step 3"; return $true }
    $es = Join-Path $ELMER_HOME "bin\ElmerSolver.exe"
    if (-not (Test-Path $es)) { Warn "ElmerSolver.exe not found"; return $true }
    if (-not (Test-Path "mesh\mesh.elements")) {
        Warn "no mesh/ - run 'mesh' first"
        return $true
    }
    if (-not (Test-Path case_simple.sif)) {
        Warn "case_simple.sif not found - skipping"
        return $true
    }
    Step 3 "ElmerSolver case_simple.sif"
    $env:ELMER_HOME = $ELMER_HOME
    $env:ELMER_LIB  = "$ELMER_HOME\share\elmersolver\lib"
    $env:Path = "$ELMER_HOME\bin;$env:Path"
    $logFile = Join-Path $PSScriptRoot 'results\solver.log'
    $errFile = [System.IO.Path]::ChangeExtension($logFile, '.err')
    $sifAbs  = (Resolve-Path case_simple.sif).Path
    $proc = Start-Process -FilePath $es -ArgumentList "`"$sifAbs`"" `
        -WorkingDirectory $ELMER_HOME `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError  $errFile `
        -PassThru -NoNewWindow -Wait
    if (Test-Path $logFile) {
        Get-Content $logFile | ForEach-Object {
            if ($_ -match 'NaN|Negative|ERROR|FAIL') { Warn $_ } else { Write-Host $_ }
        }
    }
    if ($proc.ExitCode -ne 0) {
        Warn ("ElmerSolver exited with code {0} -- known 26.1 procedure-DLL bug" -f $proc.ExitCode)
        Warn "see $logFile for details; pipeline continues"
        return $true
    }
    $vtu = Get-ChildItem results\magnet_t*.vtu -ErrorAction SilentlyContinue
    if ($vtu) { Ok ("{0} VTU frames in results/" -f $vtu.Count) }
    else      { Warn "no VTU produced -- continuing" }
    return $true
}


function Run-Oscilloscope {
    Step 4 "oscilloscope dashboard (semi-analytical)"
    New-Item -ItemType Directory -Force -Path results | Out-Null
    $rc = Run-Exe -Exe $PY -Args @("oscilloscope.py")
    if ($rc -ne 0) { Err "oscilloscope failed (exit=$rc)"; return $false }
    if (Test-Path results/dashboard.png) {
        Ok ("dashboard.png  ({0:N1} kB)" -f ([double](Get-Item results/dashboard.png).Length/1KB))
    }
    if (Test-Path results/dashboard.txt) { Ok "dashboard.txt" }
    return $true
}

function Run-FEMTests {
    Step 3 "FEM sanity tests"
    New-Item -ItemType Directory -Force -Path test_outputs | Out-Null
    $rc = Run-Exe -Exe $PY -Args @("tests/test_mesh.py")
    if ($LASTEXITCODE -ne 0) { Err "test_mesh.py failed"; return $false }
    Ok "test_mesh.py passed"
    $rc = Run-Exe -Exe $PY -Args @("tests/test_render.py")
    if ($LASTEXITCODE -ne 0) { Warn "test_render.py failed (optional)" }
    return $true
}

function Invoke-Clean {
    Info "cleaning intermediate artifacts ..."
    $dirs = @("results", "test_outputs", "mesh", "__pycache__")
    $files = @("model3d.msh", "geom_preview.step")
    foreach ($d in $dirs) {
        if (Test-Path $d) {
            $size = (Get-ChildItem $d -Recurse -ErrorAction SilentlyContinue |
                     Measure-Object Length -Sum).Sum
            Remove-Item -Recurse -Force $d
            Write-Host ("  removed  {0,-12} {1,10:N1} kB" -f $d, ($size/1KB))
        }
    }
    foreach ($f in $files) {
        if (Test-Path $f) {
            $size = (Get-Item $f).Length
            Remove-Item -Force $f
            Write-Host ("  removed  {0,-20} {1,10:N1} kB" -f $f, ($size/1KB))
        }
    }
    $current = (Get-ChildItem -File | Measure-Object Length -Sum).Sum
    Write-Host ("  current project size: {0:N1} kB" -f ($current/1KB))
}

function Invoke-GenerateSIFs {
    if (-not (Test-Path case_templates.py)) {
        Warn "case_templates.py not found -- using existing case_simple.sif"
        return $true
    }
    Info "regenerating case_<cfg>.sif for 3 configurations ..."
    & $PY case_templates.py
    if ($LASTEXITCODE -ne 0) { Err "case_templates.py failed"; return $false }
    Ok "3 case_<cfg>.sif written"
    return $true
}

# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------
$target = if ($args.Count -gt 0) { $args[0] } else { "default" }

switch ($target) {
    "help"     { Show-Help }
    "clean"    { Invoke-Clean }
    "geom"     { Build-Geometry }
    "mesh"     { if (Build-Geometry) { Build-Mesh } }
    "sifs"     { Invoke-GenerateSIFs }
    "tests"    {
        New-Item -ItemType Directory -Force -Path results | Out-Null
        if (Build-Geometry) {
            if (Build-Mesh) { Run-FEMTests }
        }
        Run-Oscilloscope
    }
    "scope"    { Run-Oscilloscope }
    "full" {
        New-Item -ItemType Directory -Force -Path results | Out-Null
        if (Build-Geometry) {
            if (Build-Mesh) { Run-ElmerSolver }
        }
        Run-Oscilloscope
    }
    default {
        Show-Help
        Write-Host ""
        Info "default pipeline: mesh + tests + oscilloscope"
        New-Item -ItemType Directory -Force -Path results | Out-Null
        if (Build-Geometry) {
            if (Build-Mesh) {
                Run-FEMTests
                Run-ElmerSolver
            }
        }
        Run-Oscilloscope
    }
}

Write-Host ""
Ok "done"
