# 排错清单

## A. Elmer 26.1 procedure DLL 加载失败（最常见）

**症状**：

```
Load: FATAL: Can't find procedure [MagnetoDynamics]
```

或更早：

```
CheckKeyword: Unlisted keyword: [magnetic vector potential 1] in section: [boundary condition 1]
ERROR:: SectionContents: Mismatch of declared and given dimension for keyword "magnetic vector potential". Ignored input: 0 0
```

**根因**（2026-01 通过 `strings` 读 `libelmersolver.dll` 字符串验证）：

```
%s\share\elmersolver
%s\..\share\elmersolver
```

Elmer 26.1 用 `<exepath>` 拼出相对路径去查找 `share\elmersolver`。
`%s` 即 `exepath`，由 `GetModuleFileNameW(NULL, ...)` 取，但
**PowerShell 用 `&` 或 `Start-Process` 启动 native exe 时，
`exepath` 解析失败**，导致 `<exepath>/../share/elmersolver` 变成
空路径，procedure DLL 就找不到了。

**已尝试且不稳定的临时方案**：

* `Set-Location "D:\Program Files\Elmer 26.1-Release"; & .\bin\ElmerSolver.exe <sif>` — 偶尔可用
* `Start-Process -WorkingDirectory "D:\..."` — 失败
* `ELMER_HOME` / `ELMER_LIB` 环境变量 — 只对 `SOLVER.KEYWORDS` 和 `elements.def` 有效，**对 procedure DLL 无效**
* 把 `MagnetoDynamics.dll` 复制到工作目录 — 失败
* 建 `share\elmersolver\lib` junction — 失败
* 建 `loadall.dll` 占位 — 未测试

**建议**：

* 升级到 Elmer ≥ 26.2（如已发布）或回退到 25.x
* 或直接在 cmd.exe 手动跑：

  ```cmd
  cd /d "D:\Program Files\Elmer 26.1-Release"
  .\bin\ElmerSolver.exe c:\Users\JosephVStalin\Desktop\PysProject\case_simple.sif
  ```

  （注意用 cmd.exe 而非 PowerShell。）

* 上报 bug：https://www.elmerfem.org/forum/

## B. Gmsh 几何

* 脚本用 **Python gmsh API**（`solenoid3d.py`），避免 `.geo` 脚本中
  `BooleanDifference` / `For ... In` 跨版本语法差异。
* 输出 `model3d.msh` (msh2.2) 强制 msh2 格式供 ElmerGrid 14 读取。
* 体积分类用包围盒（bounding-box）而不是几何中心（centre-of-mass），
  因为 fragment 之后几何中心可能跑到外部。

## C. 几何尺寸（单位 mm）

* 绕组：R_out 25, R_in 20, z [-20, +20]
* 磁铁：R 15, z [+60, +90]
* 空气：R 80, z [-50, +120]
* 磁铁 + 绕组之间 5 mm 间隙 — **对 3D ALE 偏小**，首次跑建议
  把绕组内半径改到 22 mm。

## D. Elmer sif 关键字·

* `AV` 是 base Elmer 的标量关键字（1 分量），不是矢量形式。
* `Magnetic Vector Potential` 是 MagnetoDynamics.dll 注册的 3 分量
  矢量关键字。
* `Magnetic Vector Potential 1/2/3` 是分量形式。
* 见 `case_simple.sif` 头部注释。

## E. 其他

* 自由下落时间预算：磁铁初始 z 中心 75 mm，到绕组底面 z=0 需时
  `sqrt(2 * 0.075 / 9.81) ≈ 0.124 s`。220 步 × 8e-5 s = 17.6 ms，
  磁铁还来不及走一半；要做完整 0.124 s 仿真需要约 1500 步。
* `Timestep Sizes = 8.0e-05` 是经验值；3D ALE + Direct 求解器下
  50 步/秒已是上限。
* 若 FreeCAD 宏加载多帧 .vtu 卡顿，把 `WINDOW` 参数改小（默认 6）。
