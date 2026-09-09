#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
export_step.py -- convert model3d.msh -> model3d.step for FreeCAD import.

FreeCAD's Part workbench reads .step natively (much faster than .msh).
Run this ONCE after `gmsh -3 ...` if you want a lighter geometry file:

    python export_step.py --in model3d.msh --out model3d.step

Requires:  pip install meshio
"""
import argparse
import sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="inp", default="model3d.msh")
    ap.add_argument("--out", default="model3d.step")
    args = ap.parse_args()

    try:
        import meshio
    except ImportError:
        sys.exit("meshio not installed - run:  pip install meshio")

    mesh = meshio.read(args.inp)
    meshio.write(args.out, mesh)
    print(f"[ok] wrote {args.out}  ({Path(args.out).stat().st_size/1024:.1f} kB)")

if __name__ == "__main__":
    main()
