# ---------------------------------------------------------------------------
#  run.ps1  --  complete Elmer/FEM pipeline for the falling-magnet problem
#  Tested layout:
#      c:\Users\JosephVStalin\Desktop\PysProject\
#          solenoid3d.geo
#          case.sif
#          circuit.definitions   (closed loop - Lenz drag)
#          circuit_open.definitions (open-loop reference)
#          run.ps1  (this file)
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# --- 1. Build the geometry & mesh with Gmsh -------------------------------
Write-Host "==> [1/3] Gmsh -3  build  model3d.msh" -ForegroundColor Cyan
& gmsh -3 -format msh2 -o model3d.msh solenoid3d.geo

# --- 2. Convert to Elmer internal format (format 14 -> format 2) ----------
Write-Host "==> [2/3] ElmerGrid 14 2  convert mesh" -ForegroundColor Cyan
if (Test-Path mesh) { Remove-Item -Recurse -Force mesh }
& ElmerGrid 14 2 model3d.msh -out mesh -autoclean

# --- 3. Run the transient solver ------------------------------------------
Write-Host "==> [3/3] ElmerSolver  case.sif" -ForegroundColor Cyan
& ElmerSolver case.sif

Write-Host "==> Done.  Inspect  results\  for vtu output." -ForegroundColor Green
