# 架构

## 流水线总览

```
+--------------+     +--------------+     +---------------+     +---------------+
|  gmsh (pip)   |     |  ElmerGrid   |     |  ElmerSolver  |     |   Viewer      |
|              |     |  26.1        |     |  26.1         |     |               |
|  Python API  | --> |              | --> |               | --> |               |
|  solenoid3d  |     |  14 2        |     |  case_simple  |     |  FreeCAD 1.1  |
|  .py         |     |  msh -> Elmer |     |  .sif        |     |  / pyvista    |
+--------------+     +--------------+     +---------------+     +---------------+
       |                     |                     |                     |
   model3d.msh           mesh/                  results/             view at
   (~12 MB)            (~12 MB)               *.vtu *.log          user choice
```

## 各阶段数据契约

| 阶段 | 输入 | 工具 | 输出 |
|---|---|---|---|
| 0  | （无） | `pip` | `gmsh` Python 模块 + `gmsh.bat` 启动器 |
| 1  | 尺寸参数（硬编码于脚本） | gmsh Python API | `model3d.msh`（msh2.2 格式，3 个 `Physical Volume`） |
| 2  | `model3d.msh` | `ElmerGrid 14 2` | `mesh/` 6 个文件（header, names, elements, nodes, boundary, entities.sif） |
| 3  | `mesh/` + `case_simple.sif` | `ElmerSolver` | `results/*.vtu` + `results/solver.log` |
| 4  | `results/*.vtu` | FreeCAD 宏 / pyvista | 可视化窗口 / PNG |

## 关键设计决策

### 为什么用 Python gmsh API 而非 `.geo` 脚本？

| 维度 | `.geo` 脚本 | Python gmsh API |
|---|---|---|
| 跨 gmsh 4.0–4.15 兼容性 | `BooleanFragments` / `For ... In { ov }` 语法差异大 | API 完全一致 |
| 体积分类 | centre-of-mass 在 fragment 后易误判 | 用 bounding-box 稳定可靠 |
| 调试难度 | 错误信息含 gmsh 内部 C++ traceback | Python traceback，定位精确 |
| 可嵌入 | 需要外部 gmsh.exe | 一行 `python` 命令即可 |

### 为什么把 `circuit.definitions` 用 `Include` 嵌入？

* Elmer 原生支持 `Include`，无需 elmer-circuitbuilder 库
* 多个对照实验（闭路 / 开路）只需切换一行 `Include` 即可
* `Include` 路径相对于 sif 文件所在目录解析

### 为什么用滑动窗口（默认 6 帧）做 FreeCAD 动画？

220 步瞬态结果如果一次全加载，FreeCAD 1.1 会卡顿（每帧 ≈ 1.5 万节点）。
滑动窗口只保留当前帧附近 6 帧，内存占用线性可控。

## 数据流细节

```
solenoid3d.py
    │
    │  gmsh.model.occ.{Cylinder, BooleanFragments, BooleanDifference}
    │  gmsh.model.occ.getBoundingBox(2/3, tag)
    │  gmsh.model.addPhysicalGroup(dim=3, tags=[...], tag=1|2|3)
    │  gmsh.model.addPhysicalGroup(dim=2, tags=[...], tag=1001)
    │  gmsh.model.mesh.generate(3)
    │  gmsh.write("model3d.msh")
    ▼
model3d.msh        (12.8 MB, msh2.2 ASCII)
    │
    │  ElmerGrid 14 2 model3d.msh -out mesh -autoclean
    │  (binary format conversion + boundary tagging)
    ▼
mesh/
    ├── mesh.header      (60 B,    version info)
    ├── mesh.names       (140 B,   body/boundary name table)
    ├── entities.sif     (244 B,   Body/Boundary skeleton)
    ├── mesh.nodes       (2.5 MB,  N node coords)
    ├── mesh.boundary    (450 kB,  triangle faces)
    └── mesh.elements    (9 MB,    tetrahedron connectivity)
    │
    │  ElmerSolver case_simple.sif
    │  (reads Mesh DB "." "mesh" → uses ./mesh/*)
    │  LoadInputFile → SOLVER.KEYWORDS → CheckKeyword
    │  ↓  LoadLibrary( MagnetoDynamics.dll )
    │  Procedure "MagnetoDynamics" "MagnetoDynamics"
    │  MagnetoDynamics_FEMInit, MagnetoDynamics_FEMSolve
    │  SaveScalars/Vectors → WriteData
    ▼
results/
    ├── case_simple.sif.ep          (ElmerPost compact format)
    ├── case_simple.sif.ep.vtu      (ParaView VTK Unstructured)
    ├── case_simple_t0000.vtu       (frame 0)
    ├── ...
    └── solver.log                  (human-readable solver output)
```

## 已知限制

1. **Elmer 26.1 procedure DLL 加载问题**（详见 `TROUBLESHOOTING.md`）
   - 在 PowerShell `&` 或 `Start-Process` 启动下，`<exepath>/../share/elmersolver/lib/`
     路径解析失败
   - **唯一可靠的 workaround**：在 cmd.exe 中 `cd /d` 到 Elmer 安装根目录后
     启动 `ElmerSolver.exe`

2. **磁铁 ↔ 绕组间隙仅 5 mm**：3D ALE 容易负体积，建议首次跑把
   绕组内半径改到 22 mm

3. **17.6 ms 仿真预算**：220 步 × 8e-5 s = 17.6 ms，磁铁走不到绕组底面。
   做完整 0.124 s 自由下落需要 ~1500 步
