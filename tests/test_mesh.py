"""
tests/test_mesh.py -- FEM sanity test for the gmsh mesh.

Verifies that:
  1. model3d.msh can be read back with meshio.
  2. The three body volumes (CoilBlock, Magnet, AirDomain) have the
     expected physical tag and bounding box.
  3. Each body can be rendered to a PNG via pyvista + VTK.

This test does NOT require ElmerSolver to be working.  It only
exercises steps 1 + 2 of the pipeline.
"""
from __future__ import annotations
import os
import sys
import json
import numpy as np

# pytest is optional; required only for the `pytest.mark.skipif` decorators.
try:
    import pytest  # type: ignore
except ImportError:
    pytest = None   # type: ignore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSH  = os.path.join(ROOT, 'model3d.msh')

# A no-op decorator so the file imports even without pytest
def _skipif(cond, reason=''):
    def deco(f):
        f.__skip_marker__ = (cond, reason)
        if cond:
            def skipped(*a, **kw):
                import warnings
                warnings.warn(f'SKIP {f.__name__}: {reason}')
                return None
            return skipped
        return f
    return deco
if pytest is None:
    # monkey-patch so the `@pytest.mark.skipif(...)` line still works
    class _MockMark:
        @staticmethod
        def skipif(cond, reason=''):
            return _skipif(cond, reason)
    pytest = type('pytest', (), {'mark': _MockMark})


def _have_meshio():
    try:
        import meshio  # noqa: F401
        return True
    except ImportError:
        return False


def _have_pyvista():
    try:
        import pyvista  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _have_meshio(), reason='meshio not installed')
def test_mesh_reads():
    import meshio
    m = meshio.read(MSH)
    assert m.points.shape[1] == 3
    cell_types = {c.type for c in m.cells}
    assert 'tetra' in cell_types
    assert 'triangle' in cell_types


@pytest.mark.skipif(not _have_meshio(), reason='meshio not installed')
def test_body_tags():
    import meshio
    m = meshio.read(MSH)
    phys = m.cell_data_dict['gmsh:physical']['tetra']
    unique_tags = set(phys.tolist())
    assert unique_tags == {1, 2, 3}, f'unexpected tags: {unique_tags}'


@pytest.mark.skipif(not _have_meshio(), reason='meshio not installed')
def test_body_bboxes():
    """Each body bbox must match the design dimensions."""
    import meshio
    m = meshio.read(MSH)
    phys = m.cell_data_dict['gmsh:physical']['tetra']
    tetra_cb = next(cb for cb in m.cells if cb.type == 'tetra')

    expected = {
        1: {'name': 'CoilBlock', 'r_max': 0.025, 'z_min': -0.02, 'z_max':  0.02},
        2: {'name': 'Magnet',    'r_max': 0.015, 'z_min':  0.06, 'z_max':  0.09},
        3: {'name': 'AirDomain', 'r_max': 0.080, 'z_min': -0.05, 'z_max':  0.12},
    }

    for tag, spec in expected.items():
        mask = (phys == tag)
        n = int(mask.sum())
        assert n > 0, f'Body {tag} ({spec["name"]}): 0 cells'
        cells = tetra_cb.data[mask]
        used = np.unique(cells.flatten())
        bbox = m.points[used]
        # R bound: max of sqrt(x^2 + y^2) over used points
        r_max = float(np.sqrt((bbox[:, 0]**2 + bbox[:, 1]**2).max()))
        z_min = float(bbox[:, 2].min())
        z_max = float(bbox[:, 2].max())
        tol = 1e-3
        assert abs(r_max - spec['r_max']) < tol, \
            f'Body {tag} r_max {r_max} != {spec["r_max"]}'
        assert abs(z_min - spec['z_min']) < tol, \
            f'Body {tag} z_min {z_min} != {spec["z_min"]}'
        assert abs(z_max - spec['z_max']) < tol, \
            f'Body {tag} z_max {z_max} != {spec["z_max"]}'


@pytest.mark.skipif(not _have_pyvista(), reason='pyvista not installed')
def test_pyvista_render(tmp_path):
    """Smoke test that pyvista can render the geometry to a PNG."""
    import meshio
    import pyvista as pv

    m = meshio.read(MSH)
    phys = m.cell_data_dict['gmsh:physical']['tetra']
    tetra_cb = next(cb for cb in m.cells if cb.type == 'tetra')

    bodies = {1: 'CoilBlock', 2: 'Magnet', 3: 'AirDomain'}
    pmeshes = {}
    for tag, name in bodies.items():
        mask = (phys == tag)
        cells = tetra_cb.data[mask]
        used = np.unique(cells.flatten())
        remap = -np.ones(len(m.points), dtype=int)
        remap[used] = np.arange(len(used))
        new_pts = m.points[used]
        new_cells = remap[cells]
        n = new_cells.shape[0]
        cell_array = np.empty((n, 5), dtype=np.int64)
        cell_array[:, 0] = 10  # VTK_TETRA
        cell_array[:, 1:] = new_cells
        grid = pv.UnstructuredGrid(cell_array, new_pts)
        assert grid.n_cells > 0, f'Body {tag}: pyvista grid has 0 cells'
        pmeshes[tag] = grid

    pl = pv.Plotter(off_screen=True, window_size=(800, 600))
    pl.set_background('white')
    pl.add_mesh(pmeshes[3], color='lightblue', opacity=0.10)
    pl.add_mesh(pmeshes[1], color='orange',   opacity=0.40)
    pl.add_mesh(pmeshes[2], color='red',      opacity=0.85)
    pl.add_axes()
    pl.camera_position = 'iso'
    pl.show(auto_close=False)
    out = str(tmp_path / 'mesh_preview.png')
    pl.screenshot(out)
    pl.close()
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 1000   # > 1 kB
    print(f'[ok] wrote {out}')


if __name__ == '__main__':
    # standalone execution (no pytest needed)
    print('=== FEM test ===')
    m = __import__('meshio').read(MSH)
    print(f'  points: {len(m.points)}')
    print(f'  cells:  { {c.type: len(c.data) for c in m.cells} }')
    print(f'  bbox:   {m.points.min(0).round(4).tolist()} .. '
          f'{m.points.max(0).round(4).tolist()}')
    phys = m.cell_data_dict['gmsh:physical']['tetra']
    tetra_cb = next(cb for cb in m.cells if cb.type == 'tetra')
    for tag, name in {1: 'CoilBlock', 2: 'Magnet', 3: 'AirDomain'}.items():
        mask = (phys == tag)
        n = int(mask.sum())
        cells = tetra_cb.data[mask]
        used = np.unique(cells.flatten())
        bbox = m.points[used]
        r_max = float(np.sqrt((bbox[:, 0]**2 + bbox[:, 1]**2).max()))
        print(f'  Body {tag} ({name}): {n:6d} tets  r_max={r_max:.4f}  '
              f'z=[{bbox[:,2].min():.4f}, {bbox[:,2].max():.4f}]')

    # JSON stats
    stats = {
        'points': int(len(m.points)),
        'bbox': m.points.min(0).tolist() + m.points.max(0).tolist(),
        'cells': {c.type: int(len(c.data)) for c in m.cells},
    }
    out = os.path.join(ROOT, 'test_outputs', 'fem_test_stats.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f'[ok] wrote {out}')
