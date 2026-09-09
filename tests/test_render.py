"""
tests/test_render.py -- render gmsh mesh to PNG (smoke test pyvista).

Strategy: write a per-body .vtu with meshio (which knows the proper
cell types), then read it back with pyvista.  This avoids the messy
manual cell-array construction that pyvista 0.49 made non-trivial.
"""
from __future__ import annotations
import os
import tempfile
import numpy as np

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSH   = os.path.join(ROOT, 'model3d.msh')
OUT   = os.path.join(ROOT, 'test_outputs', 'mesh_preview.png')


def main():
    import meshio
    import pyvista as pv

    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    m = meshio.read(MSH)
    phys = m.cell_data_dict['gmsh:physical']['tetra']
    tetra_cb = next(cb for cb in m.cells if cb.type == 'tetra')

    bodies = {1: 'CoilBlock', 2: 'Magnet', 3: 'AirDomain'}
    pmeshes = {}
    with tempfile.TemporaryDirectory() as tmp:
        for tag, name in bodies.items():
            mask = (phys == tag)
            # also keep triangle block (empty for sub-mesh)
            tri_cb = next(cb for cb in m.cells if cb.type == 'triangle')
            sub = meshio.Mesh(
                points=m.points,
                cells=[('tetra', tetra_cb.data[mask]),
                        ('triangle', tri_cb.data[:0])],   # empty
                cell_data={'gmsh:physical': [phys[mask], np.zeros(0, dtype=phys.dtype)]},
            )
            vtu = os.path.join(tmp, f'body_{tag}.vtu')
            meshio.write(vtu, sub)
            grid = pv.read(vtu)
            assert grid.n_cells > 0, f'Body {tag} {name}: 0 cells'
            pmeshes[tag] = grid
            print(f'  Body {tag} ({name}): {grid.n_cells} tets')

    pl = pv.Plotter(off_screen=True, window_size=(1024, 768))
    pl.set_background('white')
    pl.add_mesh(pmeshes[3], color='lightblue', opacity=0.10, label='Air')
    pl.add_mesh(pmeshes[1], color='orange',   opacity=0.40, label='Coil')
    pl.add_mesh(pmeshes[2], color='red',      opacity=0.85, label='Magnet')
    pl.add_axes()
    pl.add_legend(bcolor='white', border=True)
    pl.camera_position = 'iso'
    pl.show(auto_close=False)
    pl.screenshot(OUT)
    pl.close()
    print(f'[ok] wrote {OUT}  ({os.path.getsize(OUT)/1024:.1f} kB)')


if __name__ == '__main__':
    main()
