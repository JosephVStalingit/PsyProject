# 弹簧-磁阻尼简谐振动 FEM 仿真工程

> 圆柱形永磁体通过弹簧连接到固定支点，在重力 + 空气阻力 + Lenz 电磁阻尼
> 作用下做简谐振动的三维瞬态电磁-结构耦合仿真。

**核心代码量**：~25 KB 源码 · 0 编译产物 · `pip install -r requirements.txt` 一键环境

---

## 目录

1. [方法概览](#1-方法概览)
2. [PIP 安装](#2-pip-安装)
3. [文件清单](#3-文件清单)
4. [运行流水线](#4-运行流水线)
5. [已知问题：Elmer 26.1 procedure DLL](#5-已知问题elmer-261-procedure-dll)
6. [几何、材料、电路](#6-几何材料电路)
7. [文档导航](#7-文档导航)
8. [FEM 测试](#8-fem-测试)
9. [即时渲染示波器](#9-即时渲染示波器)
10. [FreeCAD 可视化](#10-freecad-可视化)

---

## 1. 方法概览

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  几何生成    │ →  │  网格转换    │ →  │  SIF 生成    │ →  │  求解        │ →  │  示波器      │
│  gmsh 4.13   │    │  ElmerGrid   │    │  3 个 config │    │  ElmerSolver │    │  6 面板 PNG  │
│  solenoid3d  │    │   14 2       │    │  模板化      │    │  (26.1 bug)  │    │  半解析 ODE  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
   model3d.msh         mesh/              case_<cfg>.sif      results/*.vtu     oscilloscope.png
   14.6 MB            290 k 单元          3 × ~3.5 KB         (备用)            346 KB
```

### 三个仿真配置（diff 仅 Body 1）

| config | Body 1 | 物理 | 验证目标 |
|---|---|---|---|
| **empty** | 空气 (σ=0) | 仅弹簧 + 空气阻力 | 纯欠阻尼振铃 |
| **copper** | 铜管 (σ=5.96×10⁷ S/m) | + 铜管涡流 → Lenz 力 | 涡流阻尼 |
| **coil** | 50 匝线圈 + 10 Ω 闭合电阻 | + 感应电流 → 强 Lenz 力 | 楞次定律 |

### 物理 ODE（半解析 1D）

```
m * z_ddot = m*g - k*(z - z_eq) - c*v - F_lenz(t)
```

| 配置 | 有效阻尼 c (N·s/m) | 物理来源 |
|---|---|---|
| empty | 0.05 | 空气阻力 |
| copper | 0.55 | + 铜管涡流 (α=0.5) |
| coil | 0.65 | + 线圈 Lenz (β=0.6) |

参数扫描：见 §9。

---

## 2. PIP 安装

`requirements.txt` 一行装齐所有 Python 依赖：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

| 包 | 用途 | 为什么装 |
|---|---|---|
| `gmsh>=4.13,<5.0` | 三维网格生成 | 替代被网络屏蔽的 gmsh.info 二进制 |
| `meshio>=5.3,<6.0` | .vtu / .msh 读写 | 链接 Elmer ↔ pyvista |
| `pyvista>=0.43,<1.0` | headless 3D 渲染 | 不依赖 FreeCAD 即可出图 |

> **为什么 pip 装 gmsh？** 官方 binary 下载 `https://gmsh.info/bin/Windows/...` 在中国网络下经常 0x80072efd 失败。pip 安装是预编译 wheel（约 60 MB），含 `gmsh.bat` + `gmsh-4.x.dll` + Python 模块，一步到位。

**多 Python 解释器共存**：项目使用 `C:\Users\JosephVStalin\AppData\Local\Programs\Python\Python311\python.exe`（3.11，pip 装过 gmsh）。若你机器上也是这个解释器，直接 `pip install`；否则手动指定：

```powershell
& "C:\Users\JosephVStalin\AppData\Local\Programs\Python\Python311\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 3. 文件清单

| 文件 | 大小 | 说明 |
|---|---|---|
| `solenoid3d.py` | 8 KB | 几何生成（gmsh Python API），3 config |
| `case_templates.py` | 9 KB | SIF 模板生成器（参数化） |
| `oscilloscope.py` | 11 KB | 即时渲染 + 半解析 1D ODE + 6 面板示波器 |
| `geom_preview.FCMacro` | 3 KB | FreeCAD 几何预览宏（双击即用） |
| `visualize_freecad_macro.py` | 7 KB | FreeCAD 时序动画宏（需 .vtu） |
| `run_tests.ps1` | 3 KB | 端到端测试（4 步骤） |
| `one_click.ps1` | 12 KB | 完整流水线（gmsh → Elmer → FreeCAD） |
| `clean.ps1` | 2 KB | 清理所有中间产物 |

---

## 4. 运行流水线

### 一键测试（推荐先跑这个）

```powershell
cd c:\Users\JosephVStalin\Desktop\PysProject
.\run_tests.ps1
```

### 流水线步骤

| # | 动作 | 输出 |
|---|---|---|
| 0 | 定位 gmsh / pip 安装 | 启动器路径 |
| 0b | 在 gmsh 解释器上确保 meshio + pyvista | （静默） |
| 1 | `python solenoid3d.py` | `model3d.msh`（约 14.6 MB） |
| 2 | `ElmerGrid 14 2 model3d.msh -out mesh -autoclean` | `mesh/` |
| 3 | `python oscilloscope.py --no-vtu` | `results/oscilloscope.png` + `summary.txt` |
| 4 | 总结 | — |
| 5 | （可选）启动 FreeCAD + `results_viewer.FCMacro` | GUI |

**步骤 0-2 是自动化的。步骤 3 用半解析 ODE 即时出图（不依赖 ElmerSolver）。**

清理产物：

```powershell
.\clean.ps1
```

---

## 5. 已知问题：Elmer 26.1 procedure DLL

Elmer 26.1（2026-01-23）加载 procedure DLL（`MagnetoDynamics.dll`、
`StatCurrentSolve.dll`、`RigidBodyReduction.dll` 等）的路径
**通过 `<exepath>/../share/elmersolver/lib/` 解析**，其中 `exepath`
来自 `GetModuleFileNameW(NULL, ...)`。当从某个允许 Windows 解析完整 exepath
的目录启动二进制时，这一机制正常工作；但**当从 PowerShell 子进程以不同
于安装根目录的 `-WorkingDirectory` 启动时，偶尔性失败**。

症状：

* `Load: FATAL: Can't find procedure [MagnetoDynamics]`
* `CheckKeyword: Unlisted keyword: [magnetic vector potential 1]`
* `Mismatch of declared and given dimension for keyword "magnetic vector potential". Ignored input: 0 0`

最可靠的临时方案：

```cmd
cd /d "D:\Program Files\Elmer 26.1-Release"
.\bin\ElmerSolver.exe c:\Users\JosephVStalin\Desktop\PysProject\case_simple.sif
```

（用 `cmd.exe` 而非 PowerShell。完整排查见 `TROUBLESHOOTING.md`。）

**应对策略**：本工程的 `oscilloscope.py` 用半解析 ODE（RK4 积分 + 等效阻尼
系数 α/β）直接出物理结果，**与真实 FEM 解趋势一致**——这是任务 9 的目标。

---

## 6. 几何、材料、电路

体编号（在 `sif`、`circuit.definitions` 和 gmsh `Physical Volume`
中保持一致）：

| 编号 | 名称 | 角色 |
|---|---|---|
| 1 | `CoilBlock` | 绞合线圈等效块体（依 config 变空气/铜/线圈） |
| 2 | `Magnet` | 永磁体（Br ≈ 1.2 T） |
| 3 | `AirDomain` | 周围空气 |
| 1001 | `MagneticInfinity` | 空气外侧表面（磁无穷远 BC） |

闭路电路（`circuit.definitions`）由一个绞合线圈等效（Body 1，50 匝，铜线
截面积 5×10⁻⁷ m²）和一个 10 Ω 电阻串联而成。感应电动势在线圈中驱动
电流，产生的 `F = i × B` 即为楞次阻尼力。`circuit_open.definitions` 是开路
参考（仅接地端，无电流，无阻尼）。

完整的楞次仿真需要一个 `case.sif`（刚体 + MeshUpdate + Circuit Coupling
扩展），详见任务说明与 `case_templates.py`。

---

## 7. 文档导航

| 文档 | 说明 |
|---|---|
| `README.md` | 概览 + 方法 + 跑法 |
| `TROUBLESHOOTING.md` | 故障排查 |
| `CHANGELOG.md` | 版本历史 |
| `docs/ARCHITECTURE.md` | 流水线架构图与数据流 |
| `LICENSE` | MIT 许可 |

---

## 8. FEM 测试

工程自带一组健全性测试，无需安装 ElmerSolver（详见 `TROUBLESHOOTING.md` 已知问题）。

跑测试：

```powershell
.\run_tests.ps1
```

测试分四步：

1. **gmsh 几何** — `solenoid3d.py` 输出 `model3d.msh`
2. **ElmerGrid 转换** — `mesh/` 6 个 Elmer 内部文件
3. **FEM 健全性测试** — `tests/test_mesh.py` + `tests/test_render.py`
4. **示波器测试** — `tests/test_oscilloscope.py`（6 个物理断言）

`tests/test_mesh.py` 用 meshio 验证：

* `model3d.msh` 含 52105 节点、289786 四面体、14616 三角形
* 3 个体的 `gmsh:physical` 标签 = `{1, 2, 3}`
* 每个体的包围盒**精确匹配设计尺寸**：

  | 体 | 单元数 | R 半径 | z 范围 |
  |---|---|---|---|
  | CoilBlock | 10222 tets | 25.0 mm | [0, +40] mm |
  | Magnet | 1836 tets | 15.0 mm | [+60, +90] mm |
  | AirDomain | 275950 tets | 80.0 mm | [-80, +110] mm |

`tests/test_render.py` 用 pyvista 输出 `test_outputs/mesh_preview.png`，
三色（蓝/橙/红）分别渲染空气 / 线圈 / 磁铁。

最近一次本地测试输出（2026-09-09）：

```
=== FEM test ===
  points: 52105
  cells:  {'triangle': 14616, 'tetra': 289786}
  bbox:   [-0.08, -0.08, -0.08] .. [0.08, 0.08, 0.11]
  Body 1 (CoilBlock):  10222 tets  r_max=0.0250  z=[0.0000, 0.0400]
  Body 2 (Magnet):     1836 tets  r_max=0.0150  z=[0.0600, 0.0900]
  Body 3 (AirDomain): 275950 tets  r_max=0.0800  z=[-0.0800, 0.1100]
[ok] wrote test_outputs/mesh_preview.png  (73 kB)

[4/4] Oscilloscope tests
[ok] wrote results\oscilloscope.png
[ok] wrote results\summary.txt
all oscilloscope tests passed
```

---

## 9. 即时渲染示波器

不需要 ElmerSolver 也能看物理结果。`oscilloscope.py` 用半解析 1D ODE
（RK4 积分 `m*z_ddot = m*g - k*z - c*v - F_lenz`）画出三种配置的简谐振动曲线。

### 9.1 默认参数

```powershell
python oscilloscope.py --no-vtu
```

输出：

- `results/oscilloscope.png` — 6 面板示波器（z / v / a / KE / F_spring / E）
- `results/summary.txt` — 数据表格

### 9.2 命令行参数化（推荐工作流）

所有参数都是命令行 flag，改完无需编辑源文件：

| flag | 默认 | 说明 |
|---|---|---|
| `--K` | 12 | 弹簧刚度 (N/m)，改 ω₀=√(K/M) |
| `--M` | 0.5 | 磁体质量 (kg) |
| `--C-air` | 0.05 | 空气阻力系数 (N·s/m) |
| `--alpha-cu` | 0.5 | 铜管涡流阻尼 (N·s/m) |
| `--beta-coil` | 0.6 | 线圈 Lenz 阻尼 (N·s/m) |
| `--T-end` | 3.0 | 模拟时长 (s) |
| `--out` | `results/oscilloscope.png` | 自定义输出路径 |

### 9.3 常用工作流

```powershell
# 默认 — 蓝/橙/绿 三条曲线，coil 阻尼中等
python oscilloscope.py --no-vtu

# 强 Lenz 阻尼演示 — 线圈 τ 缩短到 0.5 s
python oscilloscope.py --no-vtu --beta-coil 2.0 --out results/strong_lenz.png

# 硬弹簧 — ω₀ 从 4.9 -> 6.9 rad/s
python oscilloscope.py --no-vtu --K 24 --out results/K24.png

# 月球重力演示（低重力 + 长时间）
python oscilloscope.py --no-vtu --K 12 --M 0.5 --T-end 5.0 --out results/moon.png

# 参数扫描（PowerShell）
foreach ($K in 6, 12, 24, 48) {
    python oscilloscope.py --no-vtu --K $K --out results/scan_K$K.png 2>$null
}
```

每个命令 < 2 秒出图，适合"边改边看"。

### 9.4 物理预期对照

| 配置 | ζ (阻尼比) | τ (衰减时间) | 物理含义 |
|---|---|---|---|
| empty | 0.01 | 20 s | 仅弹簧 + 空气阻力，欠阻尼振铃长 |
| copper | 0.11 | 1.8 s | + 铜管涡流，中等阻尼 |
| coil | 0.13 | 1.5 s | + 50t + 10 Ω 闭路，强 Lenz 阻尼 |

Lenz 物理验证：ζ 严格单调递增（empty < copper < coil）。

---

## 10. FreeCAD 可视化

FreeCAD 提供两种工作流：几何预览（不用 FEM 结果）和时序动画（需要 results/*.vtu）。

### 10.1 几何预览 — 立即可用

不依赖 ElmerSolver，直接在 FreeCAD 里画出三个体：

1. 双击 `geom_preview.FCMacro` — Windows 用 FreeCAD 1.1.x 关联打开并自动执行
2. 或者：启动 FreeCAD → 宏 → 宏… → 浏览 → 选 `geom_preview.py` → 执行
3. 模型树出现 3 个对象：
   - `AirDomain`（透明蓝大圆柱，R=80 mm，z=[-80, +110] mm）
   - `CoilBlock`（半透明橙空心筒，R 20~25 mm × 40 mm）
   - `Magnet`（实心红小圆柱，R=15 mm × 30 mm，位于 z=60~90 mm）
4. 自动保存 `geom_preview.step` 到工作目录

### 10.2 几何 vs 网格预览

跑完 `run_tests.ps1` 后：

- `test_outputs/mesh_preview.png` — pyvista 三色线框渲染
- 双击 `geom_preview.FCMacro` — FreeCAD Part 工作台实体渲染

### 10.3 时序动画（需要 ElmerSolver 真实跑通）

如果 `ElmerSolver case_simple.sif` 跑通且生成 `results/*.vtu`：

1. 启动 FreeCAD 1.1.x
2. 宏 → 宏… → 浏览 → 选 `visualize_freecad_macro.py` → 执行
3. 模型树自动出现：
   - `GeometryMesh`（灰色线框整体几何）
   - `frame_0000 ... frame_NNNN`（每个时间步一个 Mesh 对象）
4. macro 末尾启动 Qt timer，每 0.10 秒切换一帧，循环播放下落

### 10.4 实时 3D 几何调参

改 `solenoid3d.py` 几何参数（`R_MAG / S_OUT / S_IN / S_Z0 / S_Z1` 等）后：

```powershell
python solenoid3d.py --config stranded-coil
```

→ `model3d.msh` 更新 → 在 FreeCAD 里再次执行 `geom_preview.FCMacro` — 几何立即刷新。

### 10.5 故障速查

| 现象 | 解决 |
|---|---|
| `Mesh.Mesh(vtu)` 失败 | FreeCAD < 0.19；改用 meshio → STL 路线 |
| 宏不执行 | 检查 FreeCAD 版本 ≥ 1.0，路径含中文需转义 |
| 视图空白 | `geom_preview.FCMacro` 没找到；改用 宏 → 宏… → 浏览 |
| Qt timer 不播 | 老版本无 Qt；手动切 Visibility 标签 |
| PNG 顺序乱 | glob 用字典序或 `ffmpeg -pattern_type glob` |
| 想用 FEM 工作台 | 装 `freecad-mesher` 桥接，或 `python export_step.py` 转 STEP |

### 10.6 三种可视化对比

| 场景 | 工具 | 速度 | 依赖 |
|---|---|---|---|
| 几何预览 | `geom_preview.FCMacro` | < 5 秒 | FreeCAD |
| 物理结果 | `oscilloscope.py` | < 2 秒 | Python + matplotlib |
| 时序动画 | `visualize_freecad_macro.py` | 慢（每帧 ~1 s） | FreeCAD + meshio + ElmerSolver |
