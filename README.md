# Falling-Magnet / Lenz-Drag  --  Elmer/FEM 3D pipeline

This project builds a complete, end-to-end **Elmer/FEM 3D magnetostatic
+ 3D ALE rigid-body** simulation pipeline.  Geometry is generated
with **Gmsh**, meshed with **ElmerGrid**, solved with **ElmerSolver**,
and visualised in **FreeCAD 1.1.x** (interactive) or **pyvista**
(headless).

The reference problem is a cylindrical NdFeB magnet falling under
gravity through a stranded solenoid that is shorted by a 10 Ohm
resistor.  With the loop closed an induced EMF drives a coil current
and the resulting `F = i x B` reproduces Lenz's drag.

---

## 1. Method overview

The pipeline has four stages, all automated by `one_click.ps1`:

```
+-----------+     +-----------+     +------------+     +---------------+
|  Gmsh     |     | ElmerGrid |     | ElmerSolver |     |  Viewer       |
|  (Python  | --> |   14 2    | --> |  (transient | --> | (FreeCAD or   |
|   API)    |     |  msh ->   |     |   or steady)|     |  pyvista)     |
|           |     |  Elmer    |     |   + circuit)|     |               |
+-----------+     +-----------+     +------------+     +---------------+
  step 1              step 2              step 3             step 5
```

### Step 1: geometry (Python gmsh API)

`solenoid3d.py` constructs four primitives with the gmsh Python
module, fragments them into a single compound, and tags the
resulting volumes by bounding-box membership:

| ID | name | role | dimensions (mm) |
|---|---|---|---|
| 1 | CoilBlock | stranded coil (hollow) | R 20-25, z [-20, +20] |
| 2 | Magnet    | permanent NdFeB        | R 15, z [+60, +90] |
| 3 | AirDomain | surrounding air        | R 80, z [-50, +120] |
| 1001 | MagneticInfinity | outer lateral surface | |

The gmsh Python API was chosen over a `.geo` script because the
fragment-then-classify pattern is identical across gmsh 4.0-4.15,
whereas the `.geo` syntax for `BooleanFragments` and `For ... In`
loops over fragment outputs differs between minor versions.

### Step 2: mesh conversion

`ElmerGrid 14 2 model3d.msh -out mesh -autoclean` reads the
msh2-format file (forced by `Mesh.MshFileVersion = 2.2` in step 1)
and writes six files into `mesh/`:

* `mesh.header`   -- version, dofs, partitioning
* `mesh.names`    -- body / boundary id <-> name table
* `mesh.elements` -- tetrahedron connectivity
* `mesh.nodes`    -- node coordinates
* `mesh.boundary` -- triangle face elements with body/boundary ids
* `entities.sif`  -- skeleton `Body` / `Boundary Condition` blocks

### Step 3: solver

`ElmerSolver case_simple.sif` is the production input.  It declares:

* one equation (magnetostatic MagnetoDynamics, A-V formulation)
* one solver (BiCGStab + ILU, nonlinear, 4 max iterations)
* three bodies (coil / magnet / air) with their materials
* one boundary (outer air surface -> Dirichlet `Magnetic Vector Potential = 0`)
* one initial condition (zero field)

For the full Lenz-drag simulation the sif is extended to two
additional solvers (`RigidBodyReduction` for the magnet's
translation and `MeshUpdate` with Velocity-Laplace smoothing) and
a coupled circuit (`circuit.definitions` -> 50-turn stranded coil
+ 10 Ohm resistor).  See `TROUBLESHOOTING.md` for the keyword list
and known issues.

### Step 4: visualisation

Two routes ship in the project:

* **FreeCAD 1.1.x (interactive)** - `results_viewer.FCMacro` opens
  the .vtu frames, builds a 3D mesh object for each time step with
  a Qt slider for scrubbing and a play/pause button.
* **pyvista (headless)** - `visualize.py` writes PNG frames; the
  included `ONE_LINER.txt` produces a single PNG per .vtu, suitable
  for batch processing.


## 2. File inventory

Source-controlled files (kept under git / version control):

| file | role |
|---|---|
| `case_simple.sif`         | Magnetostatic 3D sanity test of the Elmer pipeline |
| `circuit.definitions`     | Closed-loop circuit (50-turn coil + 10 Ohm resistor) |
| `circuit_open.definitions`| Open-loop reference (no Lenz drag) |
| `solenoid3d.py`           | Gmsh Python script (geometry + mesh) |
| `one_click.ps1`           | End-to-end pipeline (steps 0-5) |
| `run.ps1`                 | Manual pipeline (gmsh + ElmerGrid + ElmerSolver) |
| `clean.ps1`               | Remove all run-time artefacts |
| `geom_preview.py`         | Pure-Python preview (uses FreeCAD Part) |
| `geom_preview.FCMacro`    | FreeCAD macro: build preview from scratch |
| `results_viewer.FCMacro`  | FreeCAD macro: load .vtu frames, scrub slider, play/pause |
| `visualize.py`            | pyvista headless renderer |
| `visualize_freecad_macro.py` | FreeCAD macro with sliding-window Qt animation |
| `export_step.py`          | `model3d.msh -> model3d.step` (FreeCAD Part) |
| `ONE_LINER.txt`           | One-line command for FreeCAD Report View |
| `requirements.txt`        | Python pip dependencies |
| `requirements-dev.txt`    | Convenience pip alias |
| `README.md`               | This file |
| `TROUBLESHOOTING.md`      | Common failure modes |
| `.gitignore`              | Excludes generated artefacts |

Generated artefacts (not stored under git):

| file/dir | size | regenerated by |
|---|---|---|
| `model3d.msh`   | ~12 MB | step 1 (`solenoid3d.py`) |
| `mesh/`          | ~12 MB | step 2 (`ElmerGrid 14 2`) |
| `results/*.vtu`  | varies | step 3 (`ElmerSolver`) |
| `results/solver.log` | < 1 MB | step 3 |
| `geom_preview.step`   | ~9 kB  | `geom_preview.py` |

Use `clean.ps1` to delete all generated artefacts and shrink the
project back to the source-only baseline (~30 kB).

## 3. PIP installation

Three pip packages do all the heavy lifting:

| package | what it does |
|---|---|
| `gmsh`      | Generates the geometry + mesh; ships a thin Python wrapper `gmsh.bat` that loads the gmsh DLL. |
| `meshio`    | Reads `.vtu` / `.msh` and shuttles fields between Elmer and ParaView. |
| `pyvista`   | Headless 3D rendering (bundles its own VTK wheel). |

### Why pip-install gmsh?

* The official Windows installer is hosted at
  `https://gmsh.info/bin/Windows/...zip` but **the user's network
  policy blocks that domain**.
* `pip install gmsh` downloads a wheel from **PyPI** (mirrored on
  `https://pypi.tuna.tsinghua.edu.cn/simple/` for China).
* No admin rights, no PATH gymnastics, no MSI dance.

### One-shot install

```powershell
# recommended: Tsinghua mirror
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# or the short form
pip install gmsh meshio pyvista
```

`one_click.ps1` does this automatically (step 0 / 0b) and verifies
the right Python interpreter is used.

### Verify

```powershell
python -c "import gmsh, meshio, pyvista, numpy; print(gmsh.__file__)"
gmsh --version
```

You should see `gmsh 4.13.x` or newer.

## 4. Run the pipeline

```powershell
cd c:\Users\JosephVStalin\Desktop\PysProject
.\one_click.ps1
```

The script runs five steps:

| # | action | output |
|---|---|---|
| 0  | locate or pip-install gmsh | launcher path |
| 0b | ensure meshio + pyvista on the gmsh interpreter | (silent) |
| 1  | `python solenoid3d.py` | `model3d.msh` (~12 MB) |
| 2  | `ElmerGrid 14 2 model3d.msh -out mesh -autoclean` | `mesh/` |
| 3  | `ElmerSolver case_simple.sif` | `results/*.vtu` |
| 4  | summary | - |
| 5  | launch FreeCAD + `results_viewer.FCMacro` | GUI |

Steps 0-2 are deterministic.  Step 3 is the only one affected by a
known bug in Elmer 26.1 (see §5).

To clean up the artefacts and reset the project to its source-only
baseline (~30 kB):

```powershell
.\clean.ps1
```

## 5. Known issue: Elmer 26.1 procedure-DLL load path

Elmer 26.1 (2026-01-23) loads its procedure DLLs
(`MagnetoDynamics.dll`, `StatCurrentSolve.dll`,
`RigidBodyReduction.dll`, ...) from a path that is **resolved via
`<exepath>/../share/elmersolver/lib/`** where `exepath` comes from
`GetModuleFileNameW(NULL, ...)`.  This works when the binary is
launched from a directory that allows Windows to resolve the full
exepath, but **fails intermittently when the binary is started
from a PowerShell child process** with a `-WorkingDirectory`
different from the install root.

Symptoms:

* `Load: FATAL: Can't find procedure [MagnetoDynamics]`
* `CheckKeyword: Unlisted keyword: [magnetic vector potential 1]`
* `Mismatch of declared and given dimension for keyword "magnetic vector potential". Ignored input: 0 0`

Workaround that is the most reliable in this environment:

```cmd
cd /d "D:\Program Files\Elmer 26.1-Release"
.\bin\ElmerSolver.exe c:\Users\JosephVStalin\Desktop\PysProject\case_simple.sif
```

(Use `cmd.exe`, not PowerShell.)  See `TROUBLESHOOTING.md` for the
full investigation.

## 6. Geometry, materials, circuit

Body IDs (kept stable across `sif`, `circuit.definitions`, and the
gmsh `Physical Volume` declarations):

| ID | name | role |
|---|---|---|
| 1 | `CoilBlock` | Stranded solenoid winding block |
| 2 | `Magnet` | Permanent magnet (Br ~ 1.2 T) |
| 3 | `AirDomain` | Surrounding air |
| 1001 | `MagneticInfinity` | Outer lateral surface of the air (Dirichlet BC) |

The closed-loop circuit (`circuit.definitions`) closes a stranded
coil (Body 1, 50 turns, copper wire) and a 10 Ohm resistor.  An
induced EMF drives a current in the coil; the resulting
`F = i x B` is the Lenz drag.  `circuit_open.definitions` is the
open-loop reference (only the ground terminal; no current, no drag).

The full Lenz simulation therefore needs `case.sif` (not shipped -
see `case_simple.sif` for the static sanity test, then extend with
`RigidBodyReduction` + `MeshUpdate` + `Circuit Coupling`).
