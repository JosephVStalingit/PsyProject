"""
solenoid3d.py  --  Build the falling-magnet mesh entirely from the
                  gmsh Python API.  Produces model3d.msh (msh2) that
                  ElmerGrid 14 can convert directly.

Why a Python script instead of .geo?
    The .geo language has subtle syntax differences between gmsh 4.0 - 4.15,
    especially around the `For ... In { ... }` loop over fragment outputs
    and around `Physical Volume(N) += { ... }` cumulative syntax.  The
    Python API is identical across all 4.x builds and far easier to debug.

Usage:
    python solenoid3d.py            # writes ./model3d.msh
    python solenoid3d.py -o out.msh

Body ids (kept identical to case.sif):
    1 = stranded coil hollow cylinder
    2 = permanent magnet
    3 = surrounding air
    1001 = magnetic-infinity boundary (outer air surface)
"""

from __future__ import annotations
import argparse
import math
import sys
import gmsh


def build(out_path: str) -> None:
    import traceback
    try:
        _build(out_path)
    except Exception:
        traceback.print_exc()
        raise

def _build(out_path: str) -> None:
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("General.ExpertMode", 1)
    gmsh.model.add("falling_magnet")

    # ----- global mesh size --------------------------------------------
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 0.0012)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 0.004)

    # ----- dimensions -------------------------------------------------
    s_out, s_in = 0.025, 0.020
    s_lo, s_hi  = -0.02, 0.02
    m_r         = 0.015
    m_lo, m_hi  = 0.06, 0.09
    a_r         = 0.08
    a_lo, a_hi  = -0.05, 0.12

    # ----- helper to make a vertical cylinder of radius r, z in [zlo, zhi]
    def cyl(r, zlo, zhi):
        return gmsh.model.occ.addCylinder(0, 0, zlo, 0, 0, zhi - zlo, r)

    air       = cyl(a_r,   a_lo, a_hi)
    coil_out  = cyl(s_out, s_lo, s_hi)
    coil_in   = cyl(s_in,  s_lo, s_hi)
    magnet    = cyl(m_r,   m_lo, m_hi)

    # ----- 1. fragment FIRST: this splits the air cylinder along the
    #          coil + magnet, giving every region its own volume tag.
    fragments, _ = gmsh.model.occ.fragment(
        [(3, air), (3, coil_out), (3, coil_in), (3, magnet)],
        [],
        removeObject=True, removeTool=True)

    # ----- 2. cut the inner drill out of the coil-shell volumes -------
    #          (must come after fragment so tool is the correct region)
    fragments2, _ = gmsh.model.occ.cut(
        [d for d in fragments if d[0] == 3],
        [(3, coil_in)],
        removeObject=True, removeTool=True)

    gmsh.model.occ.synchronize()

    # ----- 3. classify: walk every surviving volume -------------------
    #          Use the cylinder-equivalent radius (max of |x|,|y| of the
    #          bounding box) instead of the box-corner diagonal.
    coil_tags, mag_tags, air_tags = [], [], []
    for dim, tag in fragments2:
        if dim != 3:
            continue
        bbox = gmsh.model.getBoundingBox(dim, tag)   # (xmin, ymin, zmin,
        xmin, ymin, zmin, xmax, ymax, zmax = bbox    #  xmax, ymax, zmax)
        rmax = max(abs(xmin), abs(xmax), abs(ymin), abs(ymax))
        if (zmax <= s_hi + 1e-6 and zmin >= s_lo - 1e-6
                and rmax > s_in - 1e-6 and rmax <= s_out + 1e-6):
            coil_tags.append(tag)
        elif (zmax <= m_hi + 1e-6 and zmin >= m_lo - 1e-6
              and rmax <= m_r + 1e-6):
            mag_tags.append(tag)
        else:
            air_tags.append(tag)

    # ----- 4. per-volume mesh size ------------------------------------
    # coil + air interior 0.0012 (refined), outer air + magnet 0.004.
    def size(tag, lc):
        gmsh.model.mesh.setSize(
            gmsh.model.getBoundary([(3, tag)], combined=False, oriented=False),
            lc)

    for t in coil_tags:
        size(t, 0.0012)
    for t in mag_tags + air_tags:
        size(t, 0.004)

    # ----- 5. physical groups ------------------------------------------
    # NB: setPhysicalName is purely cosmetic; the integer IDs (1,2,3) are
    # what Elmer reads from the .msh file.
    gmsh.model.addPhysicalGroup(3, coil_tags, tag=1, name="CoilBlock")
    gmsh.model.addPhysicalGroup(3, mag_tags,  tag=2, name="Magnet")
    gmsh.model.addPhysicalGroup(3, air_tags,  tag=3, name="AirDomain")

    # ----- 6. outer air boundary = magnetic-infinity surface -----------
    outer_surfs = []
    for t in air_tags:
        bnd = gmsh.model.getBoundary([(3, t)],
                                    combined=False, oriented=False)
        for dim, tag in bnd:
            if dim != 2:
                continue
            bbox = gmsh.model.getBoundingBox(2, tag)
            _, _, zmin, _, _, zmax = bbox
            # the lateral surface spans the full air z range
            if zmin < a_lo + 1e-6 and zmax > a_hi - 1e-6:
                outer_surfs.append(tag)
    # only the *lateral* surface of the outermost air ring belongs to the
    # magnetic-infinity boundary; bottom / top caps are not.
    gmsh.model.addPhysicalGroup(2, outer_surfs, tag=1001,
                                name="MagneticInfinity")

    # ----- 7. msh2 output --------------------------------------------
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Format", 1)   # ASCII

    gmsh.model.mesh.generate(3)
    gmsh.write(out_path)
    gmsh.finalize()

    # ----- 8. summary ------------------------------------------------
    print(f"[ok] wrote {out_path}")
    print(f"     coil volumes: {len(coil_tags)}")
    print(f"     magnet vols : {len(mag_tags)}")
    print(f"     air vols    : {len(air_tags)}")
    print(f"     outer surface tags: {sorted(outer_surfs)[:5]}{' ...' if len(outer_surfs) > 5 else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="model3d.msh")
    args = ap.parse_args()
    try:
        build(args.out)
    except Exception as exc:
        print(f"[err] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
