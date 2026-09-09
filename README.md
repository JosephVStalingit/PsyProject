# 落体磁铁 / 楞次阻尼 — Elmer/FEM 三维流水线

本工程搭建了一套完整的 **Elmer/FEM 三维磁静电 + 三维 ALE 刚体运动**
仿真流水线。几何用 **Gmsh** 生成，网格用 **ElmerGrid** 转换，求解用
**ElmerSolver**，可视化用 **FreeCAD 1.1.x**（交互式）或 **pyvista**
（无界面）。

参考问题：圆柱形钕铁硼磁铁在重力作用下，沿 Z 轴下落，穿过一个由 10 Ω
电阻短路的绞合螺线管。回路闭合时，感应电动势在线圈中驱动电流，产生的
洛伦兹力 `F = i × B` 复现了楞次的电磁阻尼。

---

## 1. 方法概述

流水线共四个阶段，全部由 `one_click.ps1` 自动执行：

```
+-----------+     +-----------+     +------------+     +---------------+
|  Gmsh     |     | ElmerGrid |     | ElmerSolver |     |  可视化        |
|  (Python  | --> |   14 2    | --> |  (瞬态      | --> | (FreeCAD 或   |
|   API)    |     |  msh ->   |     |   或稳态)    |     |  pyvista)     |
|           |     |  Elmer    |     |   + 电路)    |     |               |
+-----------+     +-----------+     +------------+     +---------------+
  步骤 1             步骤 2             步骤 3             步骤 5
```

### 步骤 1：几何（Python gmsh API）

`solenoid3d.py` 用 gmsh Python 模块构造四个原始体，将它们
fragment 为一个复合体，然后按包围盒分类打标签：

| 编号 | 名称 | 角色 | 尺寸（mm） |
|---|---|---|---|
| 1 | CoilBlock | 绞合线圈（空心） | R 20-25, z [-20, +20] |
| 2 | Magnet    | 永磁体（NdFeB）   | R 15, z [+60, +90] |
| 3 | AirDomain | 周围空气          | R 80, z [-50, +120] |
| 1001 | MagneticInfinity | 外侧侧面    | |

之所以选 gmsh Python API 而不是 `.geo` 脚本，是因为 fragment-then-classify
的写法在 gmsh 4.0–4.15 之间是**完全一致**的，而 `.geo` 语法里
`BooleanFragments` 和 `For ... In { ov }` 循环遍历 fragment 结果的写法
在不同小版本间存在差异。

### 步骤 2：网格转换

`ElmerGrid 14 2 model3d.msh -out mesh -autoclean` 读取 msh2 格式
（步骤 1 中通过 `Mesh.MshFileVersion = 2.2` 强制生成），并将六个
文件写到 `mesh/`：

* `mesh.header`   —— 版本、自由度、分区
* `mesh.names`    —— 体 / 边界编号 ↔ 名称映射表
* `mesh.elements` —— 四面体连接
* `mesh.nodes`    —— 节点坐标
* `mesh.boundary` —— 三角形面元（带体 / 边界编号）
* `entities.sif`  —— `Body` / `Boundary Condition` 块的骨架

### 步骤 3：求解器

`ElmerSolver case_simple.sif` 是生产输入文件，它声明：

* 一个方程（磁静电 MagnetoDynamics，A-V 公式）
* 一个求解器（BiCGStab + ILU，非线性，最多 4 次迭代）
* 三个体（线圈 / 磁铁 / 空气）及其材料
* 一个边界（外空气表面 → 狄利克雷 `Magnetic Vector Potential = 0`）
* 一个初始条件（零场）

完整楞次仿真需要把 sif 扩展为三个额外求解器（`RigidBodyReduction`
处理磁铁平动、`MeshUpdate` 做速度拉普拉斯平滑）和一个耦合电路
（`circuit.definitions` → 50 匝绞合线圈 + 10 Ω 电阻）。关键词列表
及已知问题见 `TROUBLESHOOTING.md`。

### 步骤 4：可视化

工程自带两条可视化路径：

* **FreeCAD 1.1.x（交互式）** — `results_viewer.FCMacro` 打开 .vtu
  帧，为每个时间步构建一个 3D 网格对象，配有 Qt 滑块（拖动跳帧）
  和播放 / 暂停按钮。
* **pyvista（无界面）** — `visualize.py` 写 PNG 帧；附带的
  `ONE_LINER.txt` 能为每个 .vtu 生成一张 PNG，适合批处理。

---

## 2. 文件清单

源码受控文件（Git / 版本控制跟踪）：

| 文件 | 角色 |
|---|---|
| `case_simple.sif`          | Elmer 流水线的磁静电三维健全性测试 |
| `circuit.definitions`      | 闭路电路（50 匝线圈 + 10 Ω 电阻） |
| `circuit_open.definitions` | 开路参考（无楞次阻尼） |
| `solenoid3d.py`            | Gmsh Python 脚本（几何 + 网格） |
| `one_click.ps1`            | 端到端流水线（步骤 0–5） |
| `run.ps1`                  | 手动流水线（gmsh + ElmerGrid + ElmerSolver） |
| `clean.ps1`                | 删除所有运行产物 |
| `geom_preview.py`          | 纯 Python 几何预览（FreeCAD Part） |
| `geom_preview.FCMacro`     | FreeCAD 宏：从零搭建预览 |
| `results_viewer.FCMacro`   | FreeCAD 宏：加载 .vtu 帧 + 拖动滑块 + 播放 / 暂停 |
| `visualize.py`             | pyvista 无界面渲染器 |
| `visualize_freecad_macro.py`| FreeCAD 宏 + 滑动窗口 Qt 动画 |
| `export_step.py`           | `model3d.msh → model3d.step`（FreeCAD Part） |
| `ONE_LINER.txt`            | 一行命令，粘到 FreeCAD Report View |
| `requirements.txt`         | Python pip 依赖 |
| `requirements-dev.txt`     | 便捷 pip 别名 |
| `README.md`                | 本文件 |
| `TROUBLESHOOTING.md`       | 常见故障模式 |
| `.gitignore`               | 排除生成产物 |
| `LICENSE`                  | MIT 许可协议 |
| `CHANGELOG.md`             | 版本历史 |
| `docs/`                    | 架构图、设计文档 |

生成产物（不进入版本控制）：

| 文件 / 目录 | 大小 | 谁生成 |
|---|---|---|
| `model3d.msh`        | ~12 MB | 步骤 1（`solenoid3d.py`） |
| `mesh/`              | ~12 MB | 步骤 2（`ElmerGrid 14 2`） |
| `results/*.vtu`      | 视情况 | 步骤 3（`ElmerSolver`） |
| `results/solver.log` | < 1 MB | 步骤 3 |
| `geom_preview.step`  | ~9 kB  | `geom_preview.py` |

运行 `clean.ps1` 可一键删除所有生成产物，把工程压回源码基线
（约 70 kB）。


## 3. PIP 安装

三个 pip 包承担全部重活：

| �?| 作用 |
|---|---|
| `gmsh`    | 生成几何 + 网格；自带一个轻量级 Python 启动�?`gmsh.bat`，运行时加载 gmsh DLL�?|
| `meshio`  | 读取 `.vtu` / `.msh`，在 Elmer �?ParaView 之间搬运场数据�?|
| `pyvista` | 无界�?3D 渲染（自�?VTK wheel）�?|

### 为什么用 pip �?gmsh�?

* 官方 Windows 安装包放�?`https://gmsh.info/bin/Windows/...zip`�?
  �?*用户网络策略屏蔽了该域名**�?
* `pip install gmsh` �?**PyPI** 下载 wheel（中国可走清华镜�?
  `https://pypi.tuna.tsinghua.edu.cn/simple/`）�?
* 不需要管理员权限、不需要折�?PATH、不需�?MSI�?

### 一行安�?

```powershell
# 推荐：用清华镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者直�?
pip install gmsh meshio pyvista
```

`one_click.ps1` 会自动做这件事（步骤 0 / 0b）并验证使用的是
�?gmsh 启动器同一�?Python 解释器�?

### 验证

```powershell
python -c "import gmsh, meshio, pyvista, numpy; print(gmsh.__file__)"
gmsh --version
```

应输�?`gmsh 4.13.x` 或更新版本�?

## 4. 运行流水�?

```powershell
cd c:\Users\JosephVStalin\Desktop\PysProject
.\one_click.ps1
```

脚本会依次执行五步：

| # | 动作 | 输出 |
|---|---|---|
| 0  | 定位�?pip 安装 gmsh | 启动器路�?|
| 0b | �?gmsh 解释器上确保 meshio + pyvista | （静默） |
| 1  | `python solenoid3d.py` | `model3d.msh`（~12 MB�?|
| 2  | `ElmerGrid 14 2 model3d.msh -out mesh -autoclean` | `mesh/` |
| 3  | `ElmerSolver case_simple.sif` | `results/*.vtu` |
| 4  | 总结 | �?|
| 5  | 启动 FreeCAD + `results_viewer.FCMacro` | GUI |

步骤 0�? 是确定性的。步�?3 �?Elmer 26.1 的一个已�?bug 影响
（见 §5）�?

要清理产物并把工程恢复到纯源码状态（�?70 kB）：

```powershell
.\clean.ps1
```

## 5. 已知问题：Elmer 26.1 procedure-DLL 加载路径

Elmer 26.1�?026-01-23）加�?procedure DLL（`MagnetoDynamics.dll`�?
`StatCurrentSolve.dll`、`RigidBodyReduction.dll` 等）的路�?
**通过 `<exepath>/../share/elmersolver/lib/` 解析**，其�?
`exepath` 来自 `GetModuleFileNameW(NULL, ...)`。当从某个允�?
Windows 解析完整 exepath 的目录启动二进制时，这一机制正常工作�?
�?*当从 PowerShell 子进程以不同于安装根目录�?
`-WorkingDirectory` 启动时，间歇性失�?*�?

症状�?

* `Load: FATAL: Can't find procedure [MagnetoDynamics]`
* `CheckKeyword: Unlisted keyword: [magnetic vector potential 1]`
* `Mismatch of declared and given dimension for keyword "magnetic vector potential". Ignored input: 0 0`

最可靠的临时方案：

```cmd
cd /d "D:\Program Files\Elmer 26.1-Release"
.\bin\ElmerSolver.exe c:\Users\JosephVStalin\Desktop\PysProject\case_simple.sif
```

（用 `cmd.exe` 而非 PowerShell。）完整排查�?`TROUBLESHOOTING.md`�?

## 6. 几何、材料、电�?

体编号（�?`sif`、`circuit.definitions` �?gmsh `Physical Volume`
中保持一致）�?

| 编号 | 名称 | 角色 |
|---|---|---|
| 1 | `CoilBlock` | 绞合螺线管绕组块 |
| 2 | `Magnet` | 永磁体（Br �?1.2 T�?|
| 3 | `AirDomain` | 周围空气 |
| 1001 | `MagneticInfinity` | 空气外侧侧面（狄利克�?BC�?|

闭路电路（`circuit.definitions`）由一个绞合线圈（�?1�?0 匝，
铜线）和一�?10 Ω 电阻串联而成。感应电动势在线圈中驱动电流�?
产生�?`F = i × B` 即楞次阻尼。`circuit_open.definitions` 是开�?
参考（仅接地端，无电流，无阻尼）�?

完整的楞次仿真因此需要一�?`case.sif`（未随本工程发布——见
`case_simple.sif` 的稳态健全性测试，然后�?`RigidBodyReduction` +
`MeshUpdate` + `Circuit Coupling` 扩展）�?

## 7. 文档

| 文件 | 说明 |
|---|---|
| `README.md`         | 概览 + 方法 + 跑法 |
| `TROUBLESHOOTING.md` | 故障排查 |
| `CHANGELOG.md`      | 版本历史 |
| `docs/ARCHITECTURE.md` | 流水线架构图与数据流 |
| `LICENSE`           | MIT 许可 |


## 8. FEM 测试

工程自带一组健全性测试，无需安装 ElmerSolver（详�?
`TROUBLESHOOTING.md` §A 的已知问题）�?

跑测试：

```powershell
.\run_tests.ps1
```

测试分三步：

1. **gmsh 几何** �?`solenoid3d.py` 输出 `model3d.msh`
2. **ElmerGrid 转换** �?`mesh/` 6 �?Elmer 内部文件
3. **FEM 健全性测�?* �?`tests/test_mesh.py` + `tests/test_render.py`

`tests/test_mesh.py` �?meshio 验证�?

* `model3d.msh` �?43721 节点�?42505 四面体�?2514 三角形面
* 3 个体�?`gmsh:physical` 标签 = `{1, 2, 3}`
* 每个体的包围�?*精确匹配设计尺寸**�?

  | �?| 单元�?| R 半径 | z 范围 |
  |---|---|---|---|
  | CoilBlock | 2892 tets | 25.0 mm | [-20, +20] mm |
  | Magnet | 1790 tets | 15.0 mm | [+60, +90] mm |
  | AirDomain | 237823 tets | 80.0 mm | [-50, +120] mm |

`tests/test_render.py` �?pyvista 输出 `test_outputs/mesh_preview.png`�?
三色（蓝/�?红）分别渲染空气 / 线圈 / 磁铁�?

最新一次本地测试输出（2026-09-09）：

```
=== FEM test ===
  points: 43721
  cells:  {'triangle': 12514, 'tetra': 242505}
  bbox:   [-0.08, -0.08, -0.05] .. [0.08, 0.08, 0.12]
  Body 1 (CoilBlock):   2892 tets  r_max=0.0250  z=[-0.0200, 0.0200]
  Body 2 (Magnet):      1790 tets  r_max=0.0150  z=[0.0600, 0.0900]
  Body 3 (AirDomain): 237823 tets  r_max=0.0800  z=[-0.0500, 0.1200]
[ok] wrote C:\Users\JosephVStalin\Desktop\PysProject\test_outputs\mesh_preview.png  (70.1 kB)
```
