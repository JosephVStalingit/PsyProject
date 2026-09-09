# ============================================================================
#  one_click.ps1  --  端到端流水线（几何 → 结果 → 可视化）
#
#  已知问题（Elmer 26.1 / Windows）：
#      ElmerSolver.exe 从 "<exe-dir>\share\elmersolver\lib\" 加载 procedure
#      DLL。ELMER_HOME / ELMER_LIB 环境变量不影响加载路径。当二进制从
#      安装根以外的目录启动时，加载失败，报
#      "Can't find procedure [MagnetoDynamics]"。本脚本第 3 步通过
#      -WorkingDirectory = ELMER_HOME 启动二进制来绕过此问题，
#      但在某些 Windows 版本上仍然不稳定。
#      若步骤 3 失败，请在 cmd.exe 中切换到
#      "D:\Program Files\Elmer 26.1-Release" 后用绝对路径手动跑
#      ElmerSolver.exe。
#
#  步骤：
#     0.  定位或 pip 安装 gmsh
#     0b. 在 gmsh 解释器上确保 meshio + pyvista
#     1.  python solenoid3d.py  ->  model3d.msh
#     2.  ElmerGrid 14 2        ->  mesh/（Elmer 内部格式）
#     3.  ElmerSolver case_simple.sif  ->  results/*.vtu
#     4.  总结
#     5.  启动 FreeCAD + 结果查看宏（如果已装 FreeCAD）
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# ---- Locate the Elmer 26.1 install root --------------------------------
function Find-Elmer {
    foreach ($cand in @(
        "D:\Program Files\Elmer 26.1-Release",
        "C:\Program Files\Elmer 26.1-Release",
        "C:\Program Files\Elmer",
        "$env:LOCALAPPDATA\Elmer",
        "$env:ProgramFiles\Elmer")) {
        if (Test-Path (Join-Path $cand 'bin\ElmerSolver.exe')) { return $cand }
    }
    $fromPath = (Get-Command ElmerSolver -ErrorAction SilentlyContinue).Source
    if ($fromPath) { return Split-Path (Split-Path $fromPath -Parent) -Parent }
    return $null
}
$ELMER_HOME = Find-Elmer
if (-not $ELMER_HOME) {
    Write-Host "  err  Elmer 26.1 not found - install from https://www.elmerfem.org/"
    exit 1
}
Write-Host "    -> ELMER_HOME=$ELMER_HOME"
$env:ELMER_HOME = $ELMER_HOME
$env:ELMER_LIB  = "$ELMER_HOME\share\elmersolver\lib"
# Fortran runtime DLLs (libelmersolver.dll, libgfortran-5.dll) must be on
# the load path of every procedure DLL we dlopen.
$env:Path = "$ELMER_HOME\bin;$ELMER_HOME\share\elmersolver\lib;$env:Path"

# make sure results/ exists early
New-Item -ItemType Directory -Force -Path results | Out-Null

# ---- ANSI colours (PowerShell 5 fallback) ------------------------------
function C([string]$c, [string]$s) {
    if ($Host.UI.SupportsVirtualTerminal) { return "`e[$c$s`e[0m" }
    return $s
}
function Step($n, $msg) { Write-Host (C "1;36" "[$n/5] ") -NoNewline; Write-Host $msg }
function Ok($msg)      { Write-Host (C "1;32" "  ok   ") -NoNewline; Write-Host " $msg" }
function Warn($msg)    { Write-Host (C "1;33" " warn  ") -NoNewline; Write-Host " $msg" }
function Err($msg)     { Write-Host (C "1;31" "  err  ") -NoNewline; Write-Host " $msg" }

# -----------------------------------------------------------------------
#  Helper: launch an external program and return its real exit code.
#  Bypasses PowerShell's tendency to treat stdout lines like
#  '[debug] foo' as error records (RemoteException noise) when the
#  output is piped through `& ... 2>&1 | Tee-Object`.
# -----------------------------------------------------------------------
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


# -----------------------------------------------------------------------
#  0. locate / install gmsh via pip
# -----------------------------------------------------------------------
function Find-Gmsh {
    $hit = (Get-Command gmsh -ErrorAction SilentlyContinue).Source
    if ($hit) { return $hit }
    $scriptsDirs = @()
    foreach ($py in @("python","py","python3")) {
        $p = (Get-Command $py -ErrorAction SilentlyContinue).Source
        if ($p) { $scriptsDirs += (Join-Path (Split-Path $p -Parent) "Scripts") }
    }
    $scriptsDirs += @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python314\Scripts",
        "C:\Python311\Scripts","C:\Python312\Scripts",
        "C:\Python313\Scripts","C:\Python314\Scripts")
    foreach ($d in $scriptsDirs) {
        $bat = Join-Path $d "gmsh.bat"
        if (Test-Path $bat) { return $bat }
        $sh  = Join-Path $d "gmsh"
        if (Test-Path $sh)  { return $sh  }
    }
    return $null
}
$gmsh = Find-Gmsh
# Probe the Python that owns the gmsh launcher so subsequent steps
# (gmsh Python API, meshio, pyvista) can use the same interpreter.
$PY_FOR_GMSH = $null
if ($gmsh) {
    # The launcher (gmsh.bat) is in a Python *Scripts* directory.  Walk
    # up to the python root and pick its python.exe.
    $gmshDir = Split-Path $gmsh -Parent
    if ($gmshDir -match 'Python3\d{1,2}\\Scripts$') {
        $root = $gmshDir -replace '\\Scripts$', ''
        $candidate = Join-Path $root 'python.exe'
        if (Test-Path $candidate) { $PY_FOR_GMSH = $candidate }
    }
    # Last-ditch: probe every Python install in standard locations
    if (-not $PY_FOR_GMSH) {
        foreach ($root in @(
            "$env:LOCALAPPDATA\Programs\Python\Python311",
            "$env:LOCALAPPDATA\Programs\Python\Python312",
            "$env:LOCALAPPDATA\Programs\Python\Python313",
            "$env:LOCALAPPDATA\Programs\Python\Python314",
            "C:\Python311","C:\Python312","C:\Python313","C:\Python314")) {
            $c = Join-Path $root 'python.exe'
            if (Test-Path $c) {
                # Verify the gmsh module is importable on this interpreter.
                & $c -c "import gmsh" 2>$null
                if ($LASTEXITCODE -eq 0) { $PY_FOR_GMSH = $c; break }
            }
        }
    }
}
if (-not $PY_FOR_GMSH) {
    $PY_FOR_GMSH = (Get-Command python -ErrorAction SilentlyContinue).Source
}
Write-Host "    -> PY_FOR_GMSH=$PY_FOR_GMSH"

if (-not $gmsh) {
    Step 0 "gmsh not found - installing via pip (Tsinghua mirror)"
    $py = $PY_FOR_GMSH
    if (-not $py) { Err "no python on PATH"; exit 1 }
    Write-Host "    -> pip install gmsh (using $py)"
    & $py -m pip install gmsh -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    if ($LASTEXITCODE -ne 0) {
        Warn "Tsinghua mirror failed - retrying with default pypi.org"
        & $py -m pip install gmsh --quiet
    }
    if ($LASTEXITCODE -ne 0) { Err "pip install gmsh failed"; exit 1 }
    $gmsh = Find-Gmsh
    if (-not $gmsh) { Err "gmsh installed but launcher not found"; exit 1 }
    Ok "gmsh installed via pip -> $gmsh"
} else {
    Ok "gmsh already at $gmsh"
}

# Make sure the Python we use for gmsh also has meshio + pyvista so
# visualize.py can run after the solver step.
Step 0b "ensuring meshio + pyvista on $PY_FOR_GMSH"
foreach ($pkg in @('meshio','pyvista')) {
    & $PY_FOR_GMSH -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    -> pip install $pkg"
        & $PY_FOR_GMSH -m pip install $pkg -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
        if ($LASTEXITCODE -ne 0) {
            Warn "Tsinghua mirror failed for $pkg - retrying with pypi.org"
            & $PY_FOR_GMSH -m pip install $pkg --quiet
        }
    } else {
        Write-Host "    -> $pkg already present"
    }
}

# -----------------------------------------------------------------------
#  1. gmsh  build geometry + mesh
# -----------------------------------------------------------------------
Step 1 "gmsh build geometry + mesh  ->  model3d.msh"
if (-not $PY_FOR_GMSH) { Err "no python available"; exit 1 }
$rc = Run-Exe -Exe $PY_FOR_GMSH -Args @("solenoid3d.py") -LogFile "results\gmsh.log"
if ($rc -ne 0) { Err "gmsh build failed (exit=$rc)"; exit 1 }
Ok "model3d.msh  ($([math]::Round((Get-Item model3d.msh).Length/1KB,1)) kB)"

# -----------------------------------------------------------------------
#  2. ElmerGrid  convert mesh
# -----------------------------------------------------------------------
Step 2 "ElmerGrid 14 2  ->  mesh/"
$elmergrid = (Get-Command ElmerGrid -ErrorAction SilentlyContinue).Source
if (-not $elmergrid) {
    $eg = Get-ChildItem "$ELMER_HOME\bin\ElmerGrid.exe" -ErrorAction SilentlyContinue
    if ($eg) { $elmergrid = $eg.FullName }
}
if (-not $elmergrid) { Err "ElmerGrid not found in PATH or $ELMER_HOME\bin"; exit 1 }
if (Test-Path mesh) { Remove-Item -Recurse -Force mesh }
$rc = Run-Exe -Exe (Join-Path $ELMER_HOME "bin\ElmerGrid.exe") -Args @("14","2","model3d.msh","-out","mesh","-autoclean")
if ($rc -ne 0) { Err "ElmerGrid failed (exit=$rc)"; exit 1 }
Ok "mesh/  ($((Get-ChildItem mesh\*.elements 2>$null).Count) element files)"

# -----------------------------------------------------------------------
#  3. ElmerSolver  (run with cwd=ELMER_HOME so the procedure DLLs are found)
# -----------------------------------------------------------------------
Step 3 "ElmerSolver case_simple.sif   (magnetostatic sanity check)"
$es = Get-ChildItem "$ELMER_HOME\bin\ElmerSolver.exe" -ErrorAction SilentlyContinue
if (-not $es) { Err "ElmerSolver.exe not found in $ELMER_HOME\bin"; exit 1 }
$es = $es.FullName

# PowerShell's `Push-Location` + `&` does not propagate cwd to native
# binaries reliably, so we use Start-Process which honours
# -WorkingDirectory.
$logFile  = Join-Path $PSScriptRoot 'results\solver.log'
$errFile  = [System.IO.Path]::ChangeExtension($logFile, '.err')
$sifAbs   = (Resolve-Path (Join-Path $PSScriptRoot 'case_simple.sif')).Path
$proc = Start-Process -FilePath $es -ArgumentList "`"$sifAbs`"" `
    -WorkingDirectory $ELMER_HOME `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError  $errFile `
    -PassThru -NoNewWindow -Wait

# tee the log back to console (filter ERROR/NaN)
Get-Content $logFile -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_ -match 'NaN|Negative|ERROR|FAIL') { Warn $_ } else { Write-Host $_ }
}
if ($proc.ExitCode -ne 0) {
    Err "ElmerSolver exited with code $($proc.ExitCode) - check $logFile"
    exit 1
}

$vtu = Get-ChildItem results\magnet_t*.vtu -ErrorAction SilentlyContinue
if ($vtu) { Ok "$($vtu.Count) VTU frames in results/" }
else      { Err "no VTU produced - see results\solver.log"; exit 1 }

# -----------------------------------------------------------------------
#  4. summary
# -----------------------------------------------------------------------
Step 4 "summary"
Ok "geometry  : model3d.msh  +  geom_preview.step"
Ok "mesh      : mesh/  (Elmer internal)"
Ok "circuit   : circuit.definitions  (closed loop, Lenz drag)"
$frame_count = (Get-ChildItem results\magnet_t*.vtu -ErrorAction SilentlyContinue).Count
$total_bytes = (Get-ChildItem results -Recurse -ErrorAction SilentlyContinue |
                Measure-Object Length -Sum).Sum
$total_mb    = if ($total_bytes) { [math]::Round($total_bytes / 1MB, 2) } else { 0.0 }
Ok "results   : $frame_count frames  ($total_mb MB total)"
Ok "log       : results\solver.log"

# -----------------------------------------------------------------------
#  5. launch FreeCAD results viewer (if available)
# -----------------------------------------------------------------------
Step 5 "FreeCAD results viewer"
$macro = Join-Path $PSScriptRoot "results_viewer.FCMacro"
$freecad = (Get-Command FreeCAD -ErrorAction SilentlyContinue).Source
if (-not $freecad) {
    foreach ($cand in @(
        "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe",
        "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe",
        "C:\Program Files\FreeCAD 0.20\bin\FreeCAD.exe",
        "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\FreeCAD.exe")) {
        if (Test-Path $cand) { $freecad = $cand; break }
    }
}
if ($freecad -and (Test-Path $macro)) {
    Ok "launching $freecad with $macro"
    Start-Process -FilePath $freecad -ArgumentList "`"$macro`""
} else {
    Warn "FreeCAD not found - open it manually and run:"
    Warn "  $macro"
}

Write-Host ""
Ok "pipeline complete"
