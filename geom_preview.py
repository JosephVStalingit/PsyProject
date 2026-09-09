# -*- coding: utf-8 -*-
r"""
geom_preview.py
====================================================================
Drop-in FreeCAD macro: build the falling-magnet geometry from scratch
inside FreeCAD's Part workbench.

NO EXTERNAL FILES REQUIRED.
Works even if gmsh / ElmerSolver have not been run yet, so you can
verify the geometry visually before investing simulation time.

Dimensions match solenoid3d.geo exactly (units: mm).
    coil block  : hollow cylinder, R_out 25, R_in 20, z [-20, +20]
    magnet      : solid cylinder, R 15,         z [+60, +90]
    air domain  : large cylinder, R 80,          z [-50, +120]

How to run
----------
1. FreeCAD -> Macro -> Macros ... -> Create, paste this file, Save.
2. Macro -> Execute.
3. Three colored solids appear; air is transparent, coil is orange,
   magnet is red. View cube: click 'iso' for isometric.

The macro also writes the constructed geometry to:
    c:\Users\JosephVStalin\Desktop\PysProject\geom_preview.step
so you can re-open it later with File -> Open.
"""

import os
import FreeCAD
import FreeCADGui
import Part

ROOT      = r"c:\Users\JosephVStalin\Desktop\PysProject"
STEP_OUT  = os.path.join(ROOT, "geom_preview.step")

doc = FreeCAD.newDocument("FallingMagnet")
gui = FreeCADGui

# ---- view setup ---------------------------------------------------------
gui.activeDocument().activeView().viewIsometric()
gui.activeDocument().activeView().setBackgroundType(0)   # solid colour
gui.getDocument(doc.Name).ActiveView.setColorBarDriver()

# =======================================================================
#  1. Air domain  (transparent)
# =======================================================================
air_cyl = doc.addObject("Part::Cylinder", "AirDomain")
air_cyl.Radius   = 80.0     # mm
air_cyl.Height   = 170.0    # z = -50 .. +120
air_cyl.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, -50),
    FreeCAD.Rotation(0, 0, 0, 1))

# =======================================================================
#  2. Stranded coil block (hollow cylinder)  via boolean cut
# =======================================================================
coil_outer = Part.makeCylinder(25.0, 40.0,        # R, H
                              FreeCAD.Vector(0, 0, -20),
                              FreeCAD.Vector(0, 0, 1))
coil_inner = Part.makeCylinder(20.0, 40.0,
                              FreeCAD.Vector(0, 0, -20),
                              FreeCAD.Vector(0, 0, 1))
coil_shape = coil_outer.cut(coil_inner)
coil_obj   = doc.addObject("Part::Feature", "CoilBlock")
coil_obj.Shape = coil_shape

# =======================================================================
#  3. Permanent magnet (solid cylinder)
# =======================================================================
mag_cyl = doc.addObject("Part::Cylinder", "Magnet")
mag_cyl.Radius   = 15.0
mag_cyl.Height   = 30.0
mag_cyl.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 60),
    FreeCAD.Rotation(0, 0, 0, 1))

doc.recompute()

# =======================================================================
#  4. Apply colors / transparency
# =======================================================================
def color(obj, rgb, transparency=0, line_width=1.0):
    obj.ViewObject.ShapeColor   = rgb
    obj.ViewObject.Transparency = transparency
    obj.ViewObject.LineWidth    = line_width

color(air_cyl,  (0.85, 0.92, 1.00), transparency=88)        # pale blue, ghost
color(coil_obj, (1.00, 0.55, 0.20), transparency=55)        # copper orange
color(mag_cyl,  (0.90, 0.10, 0.10), transparency=0)         # solid red

# Make coil block nicely translucent so user can see the magnet inside
coil_obj.ViewObject.DisplayMode = "Shaded"

doc.recompute()
gui.SendMsgToActiveView("ViewFit")

# =======================================================================
#  5. Save as STEP for re-use
# =======================================================================
Part.export(doc.Objects, STEP_OUT)
FreeCAD.Console.PrintMessage("[ok] geometry preview ready\n")
FreeCAD.Console.PrintMessage("[ok] saved  {}\n".format(STEP_OUT))
FreeCAD.Console.PrintMessage(
    "\n*** Now run gmsh + ElmerSolver to get results, then:\n"
    "    Macro -> Execute  visualize_freecad_macro.py  ***\n")
