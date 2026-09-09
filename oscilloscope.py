# -*- coding: utf-8 -*-
"""
oscilloscope.py  ── 三种配置的简谐振动示波器（数据 + 图像）

物理（半解析）：  m·z̈ = m·g − k(z−z₀) − c·ż + F_lenz(t)

F_lenz(t) 的来源：
    empty : F_lenz = 0           （无线圈）
    copper: F_lenz(t) = -α·ż    （铜管涡流，与速度成正比）
    coil  : F_lenz(t) = -β·ż    （线圈感应电流，与速度成正比，β 更大）

    用 RK4 积分 ODE 即可得到 z(t), v(t)。
    系数 α, β 通过解析或量纲估算（不再依赖 ElmerSolver 真实跑通）。

数据输入：
    (a) 若 results/<config>/result_t*.vtu 存在，读取其 z_Magnet(t) 序列覆盖解析解
    (b) 否则只用半解析模型

输出：
    results/oscilloscope.png   6 面板示波器
    results/summary.txt        三种配置的共振频率 / 衰减时间 / 振幅峰值
"""

from __future__ import annotations
import os, sys, glob, math, json, argparse
from pathlib import Path

import numpy as np

WORKDIR = Path(__file__).parent.resolve()
RESULTS = WORKDIR / "results"

# ====================================================================
# 物理常数（与 case_templates.py 一致）
# ====================================================================
G    = 9.81
M    = 0.5          # kg
K    = 12.0         # N/m     弹簧
C_AIR = 0.05        # N*s/m   空气阻力
ALPHA_COPPER = 0.5  # N*s/m   铜管涡流阻尼
BETA_COIL    = 0.6  # N*s/m   线圈 Lenz 阻尼（≈欠阻尼，ζ≈0.12）
Z_EQ = 0.075       # m       弹簧自然长度时磁体中心
Z0   = 0.075       # m       初位置

DT   = 0.001
T_END = 3.0
N = int(T_END / DT)

CONFIGS = ["empty", "copper", "coil"]
NICE = {"empty": "无铜管 (纯弹簧+空气阻力)",
        "copper": "铜管 (涡流阻尼)",
        "coil":   "线圈 + 10Ω 闭合 (Lenz 阻尼)"}

COLORS = {"empty": "#1f77b4",   # 蓝
          "copper": "#ff7f0e",  # 橙
          "coil":   "#2ca02c"}  # 绿

DAMPING = {"empty": C_AIR,
           "copper": C_AIR + ALPHA_COPPER,
           "coil":   C_AIR + BETA_COIL}


# ====================================================================
# ODE：m·z̈ = m·g − k(z−z_eq) − c·ż
# 坐标原点 = 弹簧自然长度位置，z_eq = 0
# ====================================================================
def simulate(config: str, dt=DT, n=N, use_vtu=False):
    """返回 t, z, v, a 四个数组。"""
    c = DAMPING[config]
    z = np.zeros(n + 1)
    v = np.zeros(n + 1)
    a = np.zeros(n + 1)
    z[0] = Z0 - Z_EQ
    v[0] = 0.0
    t = np.arange(0, (n + 1) * dt, dt)

    def f(z, v):
        return (v, (M * G - K * z - c * v) / M)

    for i in range(n):
        k1z, k1v = f(z[i], v[i])
        k2z, k2v = f(z[i] + 0.5*dt*k1z, v[i] + 0.5*dt*k1v)
        k3z, k3v = f(z[i] + 0.5*dt*k2z, v[i] + 0.5*dt*k2v)
        k4z, k4v = f(z[i] + dt*k3z, v[i] + dt*k3v)
        z[i+1] = z[i] + dt/6.0 * (k1z + 2*k2z + 2*k3z + k4z)
        v[i+1] = v[i] + dt/6.0 * (k1v + 2*k2v + 2*k3v + k4v)
        a[i+1] = (M*G - K*z[i+1] - c*v[i+1]) / M

    if use_vtu:
        z = _overlay_vtu_z(config, z)
    return t, z, v, a


def _overlay_vtu_z(config: str, z_default: np.ndarray) -> np.ndarray:
    """如果 results/<config>/result_t*.vtu 存在，读 Body 2 几何中心 z 序列覆盖 z_default。"""
    try:
        import meshio
    except ImportError:
        return z_default
    pattern = str(RESULTS / config / "result_t*.vtu")
    files = sorted(glob.glob(pattern))
    if not files:
        return z_default
    z_real = []
    for fp in files:
        try:
            m = meshio.read(fp)
        except Exception:
            return z_default
        pts = m.points
        cells = m.cells_dict
        for ctype, conn in cells.items():
            if ctype != "tetra":
                continue
            gids = m.cell_data_dict.get("gmsh:physical", {}).get(ctype, None)
            if gids is None:
                continue
            block_mean = []
            for i, tet in enumerate(conn):
                if gids[i] == 2:
                    block_mean.append(float(np.mean(pts[tet, 2])))
            if block_mean:
                z_real.append(float(np.mean(block_mean)))
            break
    if len(z_real) >= 2:
        z_real = np.array(z_real)
        t_real = np.linspace(0, T_END, len(z_real))
        t_full = np.linspace(0, T_END, len(z_default))
        return np.interp(t_full, t_real, z_real)
    return z_default


# ====================================================================
# 示波器：matplotlib 多面板
# ====================================================================
def make_oscilloscope(out_png: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out_png.parent.mkdir(parents=True, exist_ok=True)
    # 设置中文字体（Windows 优先 SimHei，否则 DejaVu Sans）
    try:
        from matplotlib import font_manager
        avail = {f.name for f in font_manager.fontManager.ttflist}
        for cand in ["SimHei", "Microsoft YaHei", "Noto Sans CJK SC", "Arial Unicode MS",
                     "PingFang SC", "WenQuanYi Zen Hei", "Source Han Sans CN"]:
            if cand in avail:
                plt.rcParams["font.sans-serif"] = [cand]
                break
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    fig, axes = plt.subplots(3, 2, figsize=(14, 9))
    titles = [
        ("z(t) 位移 / Displacement (m)",        "m"),
        ("v(t) 速度 / Velocity (m/s)",          "m/s"),
        ("a(t) 加速度 / Acceleration (m/s^2)",  "m/s^2"),
        ("KE(t) 动能 / Kinetic Energy (J)",      "J"),
        ("弹簧力 / Spring force (N)",            "N"),
        ("总能量 / Total energy (J)",            "J"),
    ]
    summary = {}

    for cfg in CONFIGS:
        t, z, v, a = simulate(cfg)
        omega0 = math.sqrt(K / M)
        c_eff = DAMPING[cfg]
        zeta = c_eff / (2 * M * omega0)
        wd = omega0 * math.sqrt(max(1 - zeta**2, 1e-9))
        T_d = 2 * math.pi / wd
        tau = 1.0 / (zeta * omega0) if zeta > 1e-6 else float("inf")
        z_max = float(np.max(np.abs(z)))
        v_max = float(np.max(np.abs(v)))
        summary[cfg] = {
            "omega0_rad_s": omega0,
            "omega_d_rad_s": wd,
            "period_s": T_d,
            "damping_ratio": zeta,
            "decay_time_s": tau,
            "z_peak_m": z_max,
            "v_peak_m_s": v_max,
        }

        F_spring = -K * z
        KE = 0.5 * M * v**2
        PE = 0.5 * K * z**2
        E = KE + PE

        axes[0, 0].plot(t, z, label=NICE[cfg], color=COLORS[cfg], lw=1.5)
        axes[0, 1].plot(t, v, label=NICE[cfg], color=COLORS[cfg], lw=1.5)
        axes[1, 0].plot(t, a, label=NICE[cfg], color=COLORS[cfg], lw=1.5)
        axes[1, 1].plot(t, KE, label=NICE[cfg], color=COLORS[cfg], lw=1.5)
        axes[2, 0].plot(t, F_spring, label=NICE[cfg], color=COLORS[cfg], lw=1.5)
        axes[2, 1].plot(t, E, label=NICE[cfg], color=COLORS[cfg], lw=1.5)

    for i, (title, unit) in enumerate(titles):
        ax = axes[i // 2, i % 2]
        ax.set_title(title)
        ax.set_xlabel("t (s)")
        ax.set_ylabel(unit)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle("弹簧-磁阻尼 简谐振动示波器  /  Spring-mass-magnetic damping oscilloscope",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote {out_png}")
    return summary


def write_summary(summary: dict, out_txt: Path):
    lines = []
    lines.append("=" * 72)
    lines.append(" Spring-magnet-damping simple-harmonic oscillator — 3-config summary")
    lines.append(" " * 18 + "(三种配置的弹簧-磁阻尼简谐振动结果对比)")
    lines.append("=" * 72)
    lines.append(f"{'config':<10} {'w0(rad/s)':>12} {'wd(rad/s)':>12} "
                 f"{'T(s)':>10} {'zeta':>8} {'tau(s)':>10} {'z_peak(m)':>10} {'v_peak(m/s)':>12}")
    lines.append("-" * 72)
    for cfg in CONFIGS:
        s = summary[cfg]
        lines.append(
            f"{cfg:<10} "
            f"{s['omega0_rad_s']:>12.4f} {s['omega_d_rad_s']:>12.4f} "
            f"{s['period_s']:>10.4f} {s['damping_ratio']:>8.4f} "
            f"{s['decay_time_s']:>10.4f} {s['z_peak_m']:>10.4f} {s['v_peak_m_s']:>12.4f}"
        )
    lines.append("-" * 72)
    lines.append("Interpretation:")
    lines.append("  - empty : spring + air drag only,           zeta ~ 0.01, tau ~ 20 s (longest ringing)")
    lines.append("  - copper: + copper-tube eddy currents,    zeta ~ 0.11, tau ~ 1.8 s (moderate)")
    lines.append("  - coil  : + 50t coil + 10 ohm closed loop, zeta ~ 0.13, tau ~ 1.5 s (Lenz damping)")
    lines.append("")
    lines.append("Physical insight:")
    lines.append("  In an open-loop coil, no current flows -> no Lenz force -> behaves like 'empty'.")
    lines.append("  Closed-loop coil gives strongest damping: induced EMF drives current in R,")
    lines.append("  producing F=i x B opposing the magnet motion (Lenz's law).")
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_txt}")


def main():
    global K, M, C_AIR, ALPHA_COPPER, BETA_COIL, T_END, N, DAMPING
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-vtu", action="store_true",
                    help="跳过 .vtu overlay（只用半解析 ODE）")
    ap.add_argument("--K", type=float, default=K,
                    help=f"弹簧刚度 N/m (默认 {K})")
    ap.add_argument("--M", type=float, default=M,
                    help=f"磁体质量 kg (默认 {M})")
    ap.add_argument("--C-air", type=float, default=C_AIR,
                    help=f"空气阻力系数 N*s/m (默认 {C_AIR})")
    ap.add_argument("--alpha-cu", type=float, default=ALPHA_COPPER,
                    help=f"铜管涡流阻尼 N*s/m (默认 {ALPHA_COPPER})")
    ap.add_argument("--beta-coil", type=float, default=BETA_COIL,
                    help=f"线圈 Lenz 阻尼 N*s/m (默认 {BETA_COIL})")
    ap.add_argument("--T-end", type=float, default=T_END,
                    help=f"模拟时长 s (默认 {T_END})")
    ap.add_argument("--out", type=str, default=None,
                    help="PNG 输出路径 (默认 results/oscilloscope.png)")
    args = ap.parse_args()

    # 临时覆盖模块级常量（不写回文件）
    K = args.K
    M = args.M
    C_AIR = args.C_air
    ALPHA_COPPER = args.alpha_cu
    BETA_COIL = args.beta_coil
    T_END = args.T_end
    N = int(T_END / DT)
    DAMPING = {"empty": C_AIR,
               "copper": C_AIR + ALPHA_COPPER,
               "coil":   C_AIR + BETA_COIL}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_png = Path(args.out) if args.out else (RESULTS / "oscilloscope.png")
    summary = make_oscilloscope(out_png)
    out_txt = out_png.with_suffix(".txt")
    write_summary(summary, out_txt)
    print()
    print(open(out_txt, encoding="utf-8").read())


if __name__ == "__main__":
    main()

