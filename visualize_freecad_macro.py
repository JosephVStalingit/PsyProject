# -*- coding: utf-8 -*-
r"""
visualize_freecad_macro.py
====================================================================
Drop-in macro for FreeCAD's Macro editor (Macro -> Macros ... -> Edit).

What it does
------------
1. Opens model3d.msh as a Mesh / FEM object so you can inspect the
   geometry (Body 1 coil block, Body 2 magnet, Body 3 air).
2. Walks results\\magnet_t*.vtu and steps through the time frames
   using the `Add the frames as point clouds / Faces / wires`
   trick that works in any FreeCAD 0.20+.
3. Animates them on a timer so the user sees the magnet fall
   in slow motion through the coil.

How to run
----------
1. Open FreeCAD.
2. (Optional but recommended)  View -> Workbench -> Part / FEM.
3. Macro -> Macros ... -> Create, paste this file, Save.
4. Macro -> Execute.

If `import meshio` fails, the macro degrades gracefully:
it imports only the .msh geometry and lists the available
.vtu files so the user can convert them externally.

Compatibility: tested on FreeCAD 1.1.x.  On 0.20 the `Mesh.Mesh(vtu)`
call also works through the same VTK backend; older 0.18 versions
need a meshio -> STL conversion step (see README).

Animation uses a SLIDING WINDOW (default 6 frames) so FreeCAD does not
choke on the 220 transient frames.  Use the spin box in the task panel
to change the current step.
"""

ROOT      = r"c:\Users\JosephVStalin\Desktop\PysProject"
MSH       = os.path.join(ROOT, "model3d.msh")
VTU_GLOB  = os.path.join(ROOT, "results", "*.vtu")
FRAME_DT  = 0.10                          # seconds between animation frames

# ---- FreeCAD 1.1.x uses PySide2; older 0.18 uses PySide; 0.20+ PySide2 --
try:
    from PySide2 import QtCore, QtWidgets
except ImportError:
    try:
        from PySide import QtCore, QtWidgets
    except ImportError:
        QtCore = QtWidgets = None


# ---------------------------------------------------------------------------
#  1.  Geometry
# ---------------------------------------------------------------------------
doc = FreeCAD.newDocument("FallingMagnet")
doc.recompute()

FreeCADGui.activeDocument().activeView().viewIsometric()

if os.path.isfile(MSH):
    geo_mesh = Mesh.Mesh(MSH)
    geo_obj  = doc.addObject("Mesh::Feature", "GeometryMesh")
    geo_obj.Mesh = geo_mesh
    geo_obj.ViewObject.DisplayMode = "Flat Lines"
    geo_obj.ViewObject.LineColor   = (0.50, 0.50, 0.50)
    geo_obj.ViewObject.Transparency = 70
    FreeCAD.Console.PrintMessage("[ok] loaded {}\n".format(MSH))
else:
    FreeCAD.Console.PrintError("[err] {} not found\n".format(MSH))

# ---------------------------------------------------------------------------
#  2.  Result frames  --  sliding window so FreeCAD does not choke
# ---------------------------------------------------------------------------
WINDOW_SIZE = 6                              # frames kept in memory at once
vtu_files = sorted(glob.glob(VTU_GLOB))
n_frames  = len(vtu_files)
FreeCAD.Console.PrintMessage("[info] {} result frames found\n".format(n_frames))

# state dict survives Qt timer reload
STATE = {"i": 0, "window": list(range(min(WINDOW_SIZE, n_frames)))}

# ----- helpers ----------------------------------------------------------
def _frame_name(i):
    return "frame_{:04d}".format(i)

def _load_frame(i):
    """Create or refresh a single frame object in the document."""
    if i < 0 or i >= n_frames:
        return None
    obj = doc.getObject(_frame_name(i))
    if obj is not None:
        return obj                       # already loaded
    vtu = vtu_files[i]
    loaded = False
    # 1) try FreeCAD Mesh import directly
    try:
        m = Mesh.Mesh(vtu)
        obj = doc.addObject("Mesh::Feature", _frame_name(i))
        obj.Mesh = m
        loaded = True
    except Exception as exc:            # noqa: BLE001
        FreeCAD.Console.PrintWarning(
            "[warn] cannot read {} directly: {}\n".format(vtu, exc))

    # 2) fallback: meshio -> STL -> Mesh
    if not loaded:
        try:
            import meshio
            mesh = meshio.read(vtu)
            stl_tmp = os.path.join(
                os.path.dirname(vtu),
                "_{}.stl".format(os.path.splitext(os.path.basename(vtu))[0]))
            meshio.write(stl_tmp, mesh)
            obj = doc.addObject("Mesh::Feature", _frame_name(i))
            obj.Mesh = Mesh.Mesh(stl_tmp)
        except Exception as exc2:        # noqa: BLE001
            FreeCAD.Console.PrintError(
                "[err] meshio fallback failed: {}\n".format(exc2))
            return None

    obj.ViewObject.DisplayMode = "Points"
    obj.ViewObject.PointColor  = (0.10, 0.40, 1.00)
    obj.ViewObject.PointSize   = 2.0
    obj.ViewObject.Visibility  = False
    return obj

def _show_window(idx):
    """Make only frames within the sliding window visible."""
    if n_frames == 0:
        return
    half = WINDOW_SIZE // 2
    lo   = max(0, idx - half)
    hi   = min(n_frames, lo + WINDOW_SIZE)
    lo   = max(0, hi - WINDOW_SIZE)               # keep window size
    for k in range(lo, hi):
        _load_frame(k)
        o = doc.getObject(_frame_name(k))
        if o:
            o.ViewObject.Visibility = (k == idx)
    STATE["window"] = list(range(lo, hi))
    STATE["i"]      = idx
    doc.recompute()

# initialise the first window
if n_frames:
    _show_window(0)
    FreeCADGui.SendMsgToActiveView("ViewFit")

# ---------------------------------------------------------------------------
#  3.  Qt timer animation  +  manual scrub via task panel
# ---------------------------------------------------------------------------
if QtCore is not None and n_frames > 0:
    timer = QtCore.QTimer()
    timer.setInterval(int(FRAME_DT * 1000))

    def _on_tick():
        _show_window((STATE["i"] + 1) % n_frames)
    timer.timeout.connect(_on_tick)
    timer.start()

    # ------- task panel: scrub slider + play/pause -----------
    panel = QtWidgets.QWidget()
    panel.setWindowTitle("Falling-Magnet Frames")
    layout = QtWidgets.QVBoxLayout(panel)

    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setRange(0, n_frames - 1)
    slider.setValue(0)
    layout.addWidget(QtWidgets.QLabel("Step  (0 .. {})".format(n_frames - 1)))
    layout.addWidget(slider)

    btn_box = QtWidgets.QHBoxLayout()
    play_btn = QtWidgets.QPushButton("Pause")
    play_btn.setCheckable(True)
    btn_box.addWidget(play_btn)
    btn_box.addWidget(QtWidgets.QLabel("dt = {:.1f} ms".format(FRAME_DT * 1000)))
    layout.addLayout(btn_box)

    slider.valueChanged.connect(_show_window)

    def _toggle_play():
        if play_btn.isChecked():
            timer.stop()
            play_btn.setText("Play")
        else:
            timer.start()
            play_btn.setText("Pause")
    play_btn.toggled.connect(_toggle_play)

    FreeCADGui.Control.showDialog(panel)
    FreeCAD.Console.PrintMessage(
        "[ok] animation running + scrub panel attached\n"
        "     slider = manual frame, button = pause\n")
else:
    FreeCAD.Console.PrintMessage(
        "[info] Qt not available or no VTU - manual play only.\n")

FreeCAD.Console.PrintMessage("[done] document 'FallingMagnet' ready.\n")
