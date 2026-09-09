"""
solenoid3d.py  --  Build the spring-oscillator mesh.

Usage (CLI):
    python solenoid3d.py                       # default: --config no-coil
    python solenoid3d.py --config no-coil
    python solenoid3d.py --config copper-tube
    python solenoid3d.py --config stranded-coil

Three configurations differ only in Body 1 (the bore region):
  no-coil       :  Body 1 = "AirInside"  (just empty air inside the bore)
  copper-tube   :  Body 1 = "CopperTube"  (solid conductor)
  stranded-coil :  Body 1 = "StrandedCoil" (geometry identical to
                   copper-tube, but flagged as a stranded coil for
                   Elmer circuit coupling)

Geometry layout (units in metres):

  Z = +0.101  AnchorPlate      fixed point (clamped at top face)
  Z = +0.099  Spring top
  Z = +0.092  Spring bottom    spring: thin elastic cylinder (Body 4)
  Z = +0.090 +---------------+  magnet top
              |    Magnet    |  Body 2, R=15mm, H=30mm
  Z = +0.060  magnet bottom
  Z =  0.000 +---------------+  coil/bore region top
              |    Body 1    |  depends on --config
  Z = -0.040  coil/bore region bottom
  Z = -0.080  AirDomain bottom
"""
from __future__ import annotations
import argparse
import sys
import gmsh


# ---- Dimensions (m) ----
R_MAG    = 0.015
MAG_Z0   = 0.060
MAG_Z1   = 0.090
R_AIR    = 0.080
AIR_Z0   = -0.080
AIR_Z1   = +0.110
S_OUT    = 0.025
S_IN     = 0.020
S_Z0     = 0.000
S_Z1     = 0.040
SPR_R_OUT = 0.008
SPR_R_IN  = 0.006
SPR_Z0   = 0.092
SPR_Z1   = 0.099
ANCH_Z0  = 0.099
ANCH_Z1  = 0.101


def cyl(r, z0, z1):
    return gmsh.model.occ.addCylinder(0, 0, z0, 0, 0, z1 - z0, r)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default='model3d.msh')
    ap.add_argument('--config',
                    choices=['no-coil', 'copper-tube', 'stranded-coil'],
                    default='no-coil')
    return ap.parse_args()

def build(out_path: str, config: str) -> None:
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 1)
    gmsh.option.setNumber('General.ExpertMode', 1)
    gmsh.model.add('spring_oscillator')

    gmsh.option.setNumber('Mesh.CharacteristicLengthMin', 0.0012)
    gmsh.option.setNumber('Mesh.CharacteristicLengthMax', 0.004)

    # ---- primitives ----
    air       = cyl(R_AIR,  AIR_Z0,  AIR_Z1)
    coil_out  = cyl(S_OUT,  S_Z0,   S_Z1)
    coil_in   = cyl(S_IN,   S_Z0,   S_Z1)
    mag       = cyl(R_MAG,  MAG_Z0, MAG_Z1)
    spr_out   = cyl(SPR_R_OUT, SPR_Z0, SPR_Z1)
    spr_in    = cyl(SPR_R_IN,  SPR_Z0, SPR_Z1)
    # anchor uses its own radius (smaller than air) to avoid Boolean
    # ambiguity when fragmenting.
    anch      = cyl(0.030, ANCH_Z0, ANCH_Z1)
    print(f'[debug] cyl tags: air={air}, coil_out={coil_out}, coil_in={coil_in}, '
          f'mag={mag}, spr_out={spr_out}, spr_in={spr_in}, anch={anch}',
          file=sys.stderr)

    # ---- bore volume (Body 1) per config ----
    if config == 'no-coil':
        bore_tag    = air
        bore_name   = 'AirInside'
    else:                       # copper-tube or stranded-coil
        bore, _ = gmsh.model.occ.cut(
            [(3, coil_out)], [(3, coil_in)],
            removeObject=True, removeTool=True)
        bore_tag  = bore[0][1]
        bore_name = 'CopperTube' if config == 'copper-tube' else 'StrandedCoil'

    # ---- spring (hollow cylinder) ----
    spring, _ = gmsh.model.occ.cut(
        [(3, spr_out)], [(3, spr_in)],
        removeObject=True, removeTool=True)
    spring_tag = spring[0][1]

    # ---- fragment everything ----
    # For 'no-coil' we use the air cylinder as the bore; for the
    # other two configs the bore is a separate volume that overlaps
    # the air, so we pass it as well.  Skip duplicates.
    fragment_input = []
    seen = set()
    for v in (air, bore_tag, mag, spring_tag, anch):
        if v not in seen:
            fragment_input.append((3, v))
            seen.add(v)
    fragments, _ = gmsh.model.occ.fragment(
        fragment_input, [], removeObject=True, removeTool=True)
    gmsh.model.occ.synchronize()
    # Re-query surviving volume tags AFTER synchronize (gmsh renumbers them)
    all_dim_tags = gmsh.model.getEntities(dim=3)

    # ---- classify by bounding box ----
    coil_vols, mag_vols, spring_vols, anch_vols, air_vols = [], [], [], [], []

    for dim, tag in all_dim_tags:
        if dim != 3:
            continue
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        rmax = max(abs(xmin), abs(xmax), abs(ymin), abs(ymax))

        if zmax > ANCH_Z0 - 1e-4 and zmin > ANCH_Z0 - 1e-4 and rmax > S_OUT:
            anch_vols.append(tag)
        elif (SPR_R_IN - 1e-4 < rmax < SPR_R_OUT + 1e-4
              and SPR_Z0 - 1e-4 < zmin and zmax < SPR_Z1 + 1e-4):
            spring_vols.append(tag)
        elif (rmax < R_MAG + 1e-4 and MAG_Z0 - 1e-4 < zmin
              and zmax < MAG_Z1 + 1e-4):
            mag_vols.append(tag)
        elif (S_Z0 - 1e-4 < zmin and zmax < S_Z1 + 1e-4
              and rmax < S_OUT + 1e-4):
            coil_vols.append(tag)
        else:
            air_vols.append(tag)

    assert coil_vols, f'no coil/air-bore volumes for {config}'
    assert mag_vols,  'no magnet volumes classified'
    assert spring_vols, 'no spring volumes classified'
    assert anch_vols, 'no anchor-plate volumes classified'

    # ---- physical groups ----
    gmsh.model.addPhysicalGroup(3, coil_vols,  tag=1, name=bore_name)
    gmsh.model.addPhysicalGroup(3, mag_vols,   tag=2, name='Magnet')
    gmsh.model.addPhysicalGroup(3, air_vols,   tag=3, name='Air')
    gmsh.model.addPhysicalGroup(3, spring_vols, tag=4, name='Spring')
    gmsh.model.addPhysicalGroup(3, anch_vols,  tag=5, name='Anchor')

    # ---- boundaries ----
    outer = []
    for t in air_vols:
        for dim, tag in gmsh.model.getBoundary([(3, t)], combined=False, oriented=False):
            if dim != 2:
                continue
            bb = gmsh.model.getBoundingBox(2, tag)
            if bb[2] < AIR_Z0 + 1e-4 and bb[5] > AIR_Z1 - 1e-4:
                outer.append(tag)
    gmsh.model.addPhysicalGroup(2, outer, tag=1001, name='MagneticInfinity')

    anch_top = []
    for t in anch_vols:
        for dim, tag in gmsh.model.getBoundary([(3, t)], combined=False, oriented=False):
            if dim != 2:
                continue
            bb = gmsh.model.getBoundingBox(2, tag)
            if bb[5] > ANCH_Z1 - 1e-4:
                anch_top.append(tag)
    gmsh.model.addPhysicalGroup(2, anch_top, tag=1002, name='AnchorFixed')

    # ---- per-volume mesh size ----
    def size(tags, lc):
        for t in tags:
            gmsh.model.mesh.setSize(
                gmsh.model.getBoundary([(3, t)], combined=False, oriented=False), lc)
    size(coil_vols + spring_vols, 0.0012)
    size(mag_vols + air_vols + anch_vols, 0.004)

    # ---- write ----
    gmsh.option.setNumber('Mesh.MshFileVersion', 2.2)
    gmsh.option.setNumber('Mesh.Format', 1)
    gmsh.model.mesh.generate(3)
    gmsh.write(out_path)
    gmsh.finalize()

    print(f'[ok] wrote {out_path}')
    print(f'     config        : {config}')
    print(f'     coil-bore vols: {len(coil_vols)} ({bore_name})')
    print(f'     magnet vols   : {len(mag_vols)}')
    print(f'     spring vols   : {len(spring_vols)}')
    print(f'     anchor vols   : {len(anch_vols)}')
    print(f'     air vols      : {len(air_vols)}')
    print(f'     outer surface : {len(outer)} faces')
    print(f'     anchor top    : {len(anch_top)} faces')


def main():
    args = parse_args()
    try:
        build(args.out, args.config)
    except Exception as exc:
        print(f'[err] {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
