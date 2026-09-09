# 变更日志

本工程的所有显著变更记录于此。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 完整的中文文档（README、TROUBLESHOOTING、ONE_LINER）
- `CHANGELOG.md` 与 `docs/ARCHITECTURE.md`
- `clean.ps1` —— 一键清理所有运行产物
- `run_tests.ps1` + `tests/test_mesh.py` + `tests/test_render.py`
  —— 完整 FEM 健全性测试流水线（不依赖 ElmerSolver）
- 测试输出 `test_outputs/mesh_preview.png`（pyvista 渲染）
- `.gitignore` —— 排除生成产物
- `requirements-dev.txt` —— `requirements.txt` 的便捷别名
- `LICENSE`（MIT）

### 变更
- `case_simple.sif` 头部加上详尽的状态注释，解释 Elmer 26.1
  procedure DLL 加载路径问题与关键字表
- `one_click.ps1` 头部注释改为中文
- README 改为完整方法文档，含 4 阶段流水线图

### 修复
- `solenoid3d.py`：用包围盒（bounding-box）替代几何中心
  （centre-of-mass）做体分类，修复 fragment 后的误判
- `circuit.definitions` / `circuit_open.definitions`：把 `$` 注释
  改为 `!`，避免被 Elmer 26.1 当 MATC 表达式解析而报错
- `case_simple.sif`：用矢量形式关键字 `Magnetic Vector Potential 1/2/3`
  替换 scalar `AV`，与 `SOLVER.KEYWORDS` 注册严格一致

## [0.1.0] - 2026-09-08

### 新增
- 初版工程结构（13 个文件）
- gmsh 几何 + ElmerGrid 网格 + ElmerSolver 求解 + FreeCAD / pyvista
  可视化端到端流水线
- Stranded 线圈电路（闭路 + 开路两个对照）

### 已知问题
- Elmer 26.1 在 PowerShell 调用下间歇性出现
  `Can't find procedure [MagnetoDynamics]` 错误
  （仅 cmd.exe 启动稳定）

[未发布]: https://example.com/pysproject/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/pysproject/releases/tag/v0.1.0
