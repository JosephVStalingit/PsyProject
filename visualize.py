#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
visualize.py -- load Elmer/FEM output into FreeCAD or pyvista.

Two usage modes:

    1) Inside FreeCAD GUI (recommended for interactive inspection):
           FreeCAD menu  ->  Macro  ->  paste the lines:
               exec(open(r"c:\\Users\\JosephVStalin\\Desktop\\PysProject\\visualize.py").read())
               visualize(mode="gui")

    2) Headless / no-FreeCAD fallback (uses meshio + pyvista):
           python visualize.py --mode pyvista --msh model3d.msh --vtu results\\magnet_t0001.vtu --out frame.png
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ----------------------------------------------------------------------
#  MODE A  --  FreeCAD GUI
# ----------------------------------------------------------------------
def visualize_freecad_gui(msh=None, vtu_dir=None, field="magnetic flux density"):
    """Open the mesh + a result frame inside the running FreeCAD instance."""
    import FreeCAD
    import FreeCADGui
    import Mesh
    doc = FreeCAD.newDocument("FallingMagnet")
    FreeCADGui.activeDocument().activeView().viewIsometric()

    # ---- 1. import Gmsh mesh as a Mesh object -----------------------------
    msh = msh or str(ROOT / "model3d.msh")
    if os.path.isfile(msh):
        fem_mesh = Mesh.Mesh(msh)
        mesh_part = doc.addObject("Mesh::Feature", "GeometryMesh")
        mesh_part.Mesh = fem_mesh
        mesh_part.ViewObject.DisplayMode = "Flat Lines"
        FreeCADGui.SendMsgToActiveView("ViewFit")
        print(f"[ok] loaded {msh}")
    else:
        print(f"[warn] {msh} not found - skip geometry import")

    # ---- 2. import the first .vtu step ------------------------------------
    vtu_dir = vtu_dir or str(ROOT / "results")
    if os.path.isdir(vtu_dir):
        vtus = sorted(Path(vtu_dir).glob("*.vtu"))
        if vtus:
            print(f"[info] loading first frame: {vtus[0].name}")
            try:
                mesh_obj = doc.addObject("Mesh::Feature", vtus[0].stem)
                mesh_obj.Mesh = Mesh.Mesh(str(vtus[0]))
                mesh_obj.ViewObject.DisplayMode = "Points"
            except Exception as exc:                # noqa: BLE001
                print(f"[warn] cannot import VTU directly: {exc}")
                print("       use MODE B (pyvista) instead.")
    doc.recompute()
    FreeCADGui.SendMsgToActiveView("ViewFit")
    print("[ok] FreeCAD document 'FallingMagnet' populated.")


# ----------------------------------------------------------------------
#  MODE B  --  headless, pyvista + meshio
# ----------------------------------------------------------------------
def visualize_pyvista(msh, vtu_glob, out, field="magnetic flux density",
                     off_screen=True):
    """Render one or many frames as PNG without FreeCAD."""
    try:
        import meshio
    except ImportError:
        sys.exit("meshio not installed - run:  pip install meshio pyvista")
    try:
        import pyvista as pv
    except ImportError:
        sys.exit("pyvista not installed - run:  pip install meshio pyvista")

    msh_path = Path(msh) if msh else (ROOT / "model3d.msh")
    if not msh_path.is_file():
        sys.exit(f"mesh file not found: {msh_path}")

    # ---- 1. geometry only (transparent wireframe) -----------------------
    geo = meshio.read(str(msh_path))
    grid = pv.from_meshio(geo)
    pl = pv.Plotter(off_screen=off_screen)
    pl.set_background("white")
    pl.add_mesh(grid, style="wireframe", color="grey", opacity=0.30)

    # ---- 2. one or more vtu result files --------------------------------
    if vtu_glob:
        if Path(vtu_glob).is_absolute():
            vtus = sorted(Path().glob(vtu_glob))
        else:
            vtus = sorted((ROOT / vtu_glob).parent.glob(Path(vtu_glob).name))
        if not vtus:
            sys.exit(f"no vtu files match {vtu_glob}")
        for vtu in vtus:
            res = meshio.read(str(vtu))
            res_grid = pv.from_meshio(res)
            avail = res.point_data.keys()
            pick = field if field in avail else (next(iter(avail)) if avail else None)
            if pick is None:
                print(f"[warn] {vtu.name} has no point data")
                continue
            pl.add_mesh(res_grid, scalars=pick, cmap="viridis",
                        smooth_shading=True, show_scalar_bar=True,
                        opacity=0.85, name=vtu.stem)

    pl.add_axes()
    pl.camera_position = "iso"
    pl.show(auto_close=False)
    pl.screenshot(out, window_size=(1280, 800))
    print(f"[ok] wrote {out}")


# ----------------------------------------------------------------------
#  CLI
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Visualize Elmer/FEM output")
    ap.add_argument("--mode", choices=["gui", "pyvista"], default="pyvista")
    ap.add_argument("--msh",  default=None, help="path to model3d.msh")
    ap.add_argument("--vtu",  default="results/magnet_t*.vtu",
                    help="glob for vtu result files (pyvista mode)")
    ap.add_argument("--vtu-dir", default=None,
                    help="directory of vtu results (gui mode)")
    ap.add_argument("--field", default="magnetic flux density",
                    help="point-data field to colour by")
    ap.add_argument("--out", default="frame.png",
                    help="output PNG (pyvista mode)")
    args = ap.parse_args()

    if args.mode == "gui":
        visualize_freecad_gui(msh=args.msh, vtu_dir=args.vtu_dir,
                              field=args.field)
    else:
        visualize_pyvista(msh=args.msh, vtu_glob=args.vtu,
                          out=args.out, field=args.field)


if __name__ == "__main__":
    main()
