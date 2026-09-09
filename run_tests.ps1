# ============================================================================
#  run_tests.ps1  --  跑全部 FEM 测试
#
#  测试不依赖 ElmerSolver（procedure DLL 加载问题已记录于
#  TROUBLESHOOTING.md），仅验证流水线步骤 1-2 的几何 / 网格 / 可视化。
#
#  返回码：0 = 全部通过；1 = 至少一项失败。
# ============================================================================
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

# Pick the Python that owns the gmsh installation
$PY = $null
foreach ($cand in @(
    "C:\Users\JosephVStalin\AppData\Local\Programs\Python\Python311\python.exe",
    "C:\Python314\python.exe",
    "python")) {
    $p = Get-Command $cand -ErrorAction SilentlyContinue
    if ($p) { $PY = $p.Source; break }
}
if (-not $PY) {
    Write-Host "  err  python not found" -ForegroundColor Red
    exit 1
}
Write-Host "    -> using $PY" -ForegroundColor Cyan

# 1. Build the mesh (gmsh)
Write-Host ""
Write-Host "[1/3] gmsh build" -ForegroundColor Cyan
& $PY solenoid3d.py 2>&1 | Tee-Object -FilePath test_outputs\gmsh.log | Select-Object -Last 4
if (-not (Test-Path model3d.msh)) {
    Write-Host "  err  model3d.msh not produced" -ForegroundColor Red
    exit 1
}
Write-Host ("  ok   model3d.msh  ({0:N1} MB)" -f ([double](Get-Item model3d.msh).Length/1MB)) -ForegroundColor Green

# 2. Convert mesh (ElmerGrid)
Write-Host ""
Write-Host "[2/3] ElmerGrid 14 2" -ForegroundColor Cyan
if (Test-Path mesh) { Remove-Item -Recurse -Force mesh }
& ElmerGrid 14 2 model3d.msh -out mesh -autoclean 2>&1 | Select-Object -First 3
if (-not (Test-Path mesh\mesh.elements)) {
    Write-Host "  err  mesh\ not produced" -ForegroundColor Red
    exit 1
}
Write-Host ("  ok   mesh\  ({0} element files)" -f (Get-ChildItem mesh\*.elements).Count) -ForegroundColor Green

# 3. Run the FEM sanity tests
Write-Host ""
Write-Host "[3/4] FEM tests" -ForegroundColor Cyan
New-Item -ItemType Directory -Force test_outputs | Out-Null
& $PY tests/test_mesh.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  err  test_mesh.py failed" -ForegroundColor Red
    exit 1
}
& $PY tests/test_render.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  err  test_render.py failed" -ForegroundColor Red
    exit 1
}

# 4. Oscilloscope tests (spring-magnet damping 3-config)
Write-Host ""
Write-Host "[4/4] Oscilloscope tests" -ForegroundColor Cyan
& $PY -c "import sys; sys.path.insert(0, '.'); from tests.test_oscilloscope import test_damping_monotonic, test_period_in_range, test_peak_decreasing, test_decay_rate, test_oscilloscope_png, test_summary_txt; test_damping_monotonic(); test_period_in_range(); test_peak_decreasing(); test_decay_rate(); test_oscilloscope_png(); test_summary_txt(); print('all oscilloscope tests passed')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  err  test_oscilloscope.py failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  ok   all FEM tests passed" -ForegroundColor Green
Write-Host ""
Write-Host "Outputs in test_outputs/:" -ForegroundColor Cyan
Get-ChildItem test_outputs | Format-Table Name, Length -AutoSize
Write-Host ""
Write-Host "Outputs in results/:" -ForegroundColor Cyan
Get-ChildItem results -ErrorAction SilentlyContinue | Format-Table Name, Length -AutoSize
