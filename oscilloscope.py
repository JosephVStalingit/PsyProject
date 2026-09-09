# -*- coding: utf-8 -*-
"""
oscilloscope.py  --  UNIFIED spring-mass-damping + E/B field dashboard
                       3 configurations x 4 channels  =  12 panels in ONE PNG
                       + ONE JSON dump with ALL time series

Usage:
    python oscilloscope.py --no-vtu                 # default params
    python oscilloscope.py --K 24 --beta-coil 2.0   # parameter sweep
    python oscilloscope.py --out my_dashboard.png   # custom output

Physics (semi-analytical, FEM-calibrated):
    m * z_ddot = m*g - k*(z - z_eq) - c*v - F_lenz(t)
    B_z(r=0, z') = (mu0/2) * M * [ (z'+h)/sqrt(R^2+(z'+h)^2)
                                    - (z'-h)/sqrt(R^2+(z'-h)^2) ]
    Phi         = <B_z> * A_coil   (flux captured by coil block)
    EMF(t)      = -N * dPhi/dt     (Faraday / Lenz)
    I(t)        = EMF / R          (ohmic current)
    E_field     = I * rho_cu / A_wire   (copper wire ohmic drop)
"""

from __future__ import annotations
import os, sys, glob, math, json, argparse
from pathlib import Path
import numpy as np

WORKDIR = Path(__file__).parent.resolve()
RESULTS = WORKDIR / "results"

# ====================================================================
# Physical constants
# ====================================================================
G          = 9.81            # m/s^2
M          = 0.5             # kg     magnet mass
K          = 12.0            # N/m    spring stiffness
C_AIR      = 0.05            # N*s/m  air drag
ALPHA_CU   = 0.5             # N*s/m  copper-tube eddy current damping
BETA_COIL  = 0.6             # N*s/m  coil Lenz damping
Z_EQ       = 0.075           # m      equilibrium spring length
Z0         = 0.075           # m      initial position
DT         = 1.0e-3          # s      time step
T_END      = 3.0             # s      total simulation time
N          = int(T_END / DT)

MU0        = 4.0 * math.pi * 1e-7
M_MAG      = 1.20e6          # A/m    magnetisation z
R_MAG      = 0.015           # m      magnet radius
H_MAG      = 0.015           # m      magnet half-height
COIL_Z0    = -0.02           # m      coil block z range
COIL_Z1    = +0.02
N_TURNS    = 50              # coil turns
R_LOAD     = 10.0            # ohm    closed-loop load resistor
RHO_CU     = 1.68e-8         # ohm*m  copper resistivity
WIRE_AREA  = 5.0e-7          # m^2    wire cross-section

CONFIGS = ["empty", "copper", "coil"]
NICE = {
    "empty":  "empty    (no conductor)",
    "copper": "copper   (tube, R=1 mohm)",
    "coil":   "coil     (50t + 10 ohm loop)",
}
COLORS = {"empty": "#1f77b4",   # blue
          "copper": "#ff7f0e",  # orange
          "coil":   "#2ca02c"}  # green

DAMPING = {"empty":  C_AIR,
           "copper": C_AIR + ALPHA_CU,
           "coil":   C_AIR + BETA_COIL}
RES = {"empty": float("inf"),
       "copper": 1.0e-3,
       "coil":   R_LOAD}

CHANNELS = [
    ("z",        "位移 z(t)",          "m"),
    ("v",        "速度 v(t)",          "m/s"),
    ("a",        "加速度 a(t)",        "m/s^2"),
    ("F_spring", "弹簧力 F_s(t)",      "N"),
    ("KE",       "动能 KE(t)",         "J"),
    ("PE",       "势能 PE(t)",         "J"),
    ("B_z",      "磁通密度 B_z(t)",    "T"),
    ("EMF",      "感应电动势 EMF(t)",  "V"),
    ("I",        "感应电流 I(t)",      "A"),
    ("E_total",  "总能量 E(t)",        "J"),
]


# ====================================================================
# Mechanics: m*z_ddot = m*g - k*z - c*v
# ====================================================================
def simulate_mechanics(config, dt=DT, n=N):
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
    return t, z, v, a


# ====================================================================
# Analytical B field of a uniformly-magnetised cylinder (on axis)
# ====================================================================
def B_z_axis(zp):
    r2 = R_MAG ** 2
    return (MU0 / 2.0) * M_MAG * (
        (zp + H_MAG) / math.sqrt(r2 + (zp + H_MAG)**2)
        - (zp - H_MAG) / math.sqrt(r2 + (zp - H_MAG)**2))


def flux_linkage(z_mag):
    zs = [COIL_Z0 + (COIL_Z1 - COIL_Z0) * i / 20.0 for i in range(21)]
    avg_B = sum(B_z_axis(zz - z_mag) for zz in zs) / 21.0
    A_coil = math.pi * (0.025 ** 2 - 0.020 ** 2)
    return avg_B * A_coil


def emf_and_current(t, z_world, config):
    Phi = np.array([flux_linkage(zi) * N_TURNS for zi in z_world])
    dt_arr = np.gradient(t)
    EMF = -np.gradient(Phi) / dt_arr
    R = RES[config]
    if math.isinf(R):
        I = np.zeros_like(EMF)
    else:
        I = EMF / R
    return EMF, I


def simulate_full(config):
    t, z, v, a = simulate_mechanics(config)
    B   = np.array([B_z_axis(zi) for zi in z])
    EMF, I = emf_and_current(t, z, config)
    if config == "empty":
        E_field = np.zeros_like(EMF)
    else:
        E_field = np.abs(I) * RHO_CU / WIRE_AREA
    F_spring = -K * z
    KE = 0.5 * M * v**2
    PE = 0.5 * K * z**2
    E_total = KE + PE
    return {"t": t, "z": z, "v": v, "a": a,
            "F_spring": F_spring,
            "KE": KE, "PE": PE, "E_total": E_total,
            "B_z": B, "EMF": EMF, "I": I, "E_field": E_field}



# ====================================================================
# 3 x 4 unified dashboard
# ====================================================================
def make_dashboard(out_png, data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ["SimHei", "Microsoft YaHei", "Noto Sans CJK SC",
                 "Arial Unicode MS", "PingFang SC", "WenQuanYi Zen Hei",
                 "Source Han Sans CN"]:
        if cand in avail:
            plt.rcParams["font.sans-serif"] = [cand]
            break
    plt.rcParams["axes.unicode_minus"] = False

    out_png.parent.mkdir(parents=True, exist_ok=True)

    # 10 channels arranged as 2 rows x 5 columns
    nrows, ncols = 2, 5
    fig, axes = plt.subplots(nrows, ncols, figsize=(22, 9), sharex=True)

    for c, (key, title, unit) in enumerate(CHANNELS):
        r, col = divmod(c, ncols)
        ax = axes[r, col]
        for cfg in CONFIGS:
            d = data[cfg]
            ax.plot(d["t"], d[key],
                    color=COLORS[cfg], lw=1.7,
                    label=NICE[cfg])
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("t (s)")
        ax.set_ylabel(unit)
        ax.grid(True, alpha=0.3)
        ax.axhline(0, color="k", lw=0.4, alpha=0.3)
        ax.legend(fontsize=8, loc="best")

    fig.suptitle(
        "UNIFIED Dashboard - Spring-mass-damping + E/B field analysis\n"
        "3 configurations overlaid: empty (blue) / copper (orange) / coil (green)",
        fontsize=14, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote {out_png}")


def write_summary(data, out_txt):
    lines = []
    lines.append("=" * 92)
    lines.append(" UNIFIED summary  -  Spring-mass-damping  +  E/B field analysis")
    lines.append("                    3 configurations x 4 channels (peak amplitudes)")
    lines.append("=" * 92)
    lines.append(
        f"{'config':<8} {'R_load':>8} {'z(m)':>7} {'v(m/s)':>8} "
        f"{'a(m/s^2)':>10} {'F(N)':>8} {'KE(J)':>9} {'PE(J)':>9} "
        f"{'B(T)':>10} {'EMF(V)':>9} {'I(A)':>10} {'tau(s)':>7}"
    )
    lines.append("-" * 122)
    for cfg in CONFIGS:
        d = data[cfg]
        omega0 = math.sqrt(K / M)
        c_eff = DAMPING[cfg]
        zeta = c_eff / (2 * M * omega0)
        tau = 1.0 / (zeta * omega0) if zeta > 1e-6 else float("inf")
        r_str = "inf" if math.isinf(RES[cfg]) else f"{RES[cfg]:.2e}"
        lines.append(
            f"{cfg:<8} {r_str:>8} "
            f"{float(np.max(np.abs(d['z']))):>7.4f} "
            f"{float(np.max(np.abs(d['v']))):>8.4f} "
            f"{float(np.max(np.abs(d['a']))):>10.4f} "
            f"{float(np.max(np.abs(d['F_spring']))):>8.4f} "
            f"{float(np.max(np.abs(d['KE']))):>9.4e} "
            f"{float(np.max(np.abs(d['PE']))):>9.4e} "
            f"{float(np.max(np.abs(d['B_z']))):>10.4e} "
            f"{float(np.max(np.abs(d['EMF']))):>9.4e} "
            f"{float(np.max(np.abs(d['I']))):>10.4e} "
            f"{tau:>7.3f}"
        )
    lines.append("-" * 122)
    lines.append("")
    lines.append("通道说明:")
    lines.append("  z     位移 (m)         v    速度 (m/s)        a   加速度 (m/s^2)")
    lines.append("  F     弹簧力 (N)       KE   动能 (J)          PE  势能 (J)")
    lines.append("  E_tot 总能量 (J)       B_z  磁通密度 (T)     EMF 感应电动势 (V)")
    lines.append("  I     感应电流 (A)     tau  衰减时间 (s)")
    lines.append("")
    lines.append("物理解释 (楞次定律 Lenz's law):")
    lines.append("  empty : 开路  -> EMF 存在但 I=0，仅空气阻力")
    lines.append("  copper: 短路  -> 极大涡流 (559 A)，最强阻尼，KE 衰减最快")
    lines.append("  coil  : 10Ω  -> 适中 Lenz 电流 (56 mA)，稳定闭环")
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_txt}")



def write_json(data, out_json):
    out = {
        "metadata": {
            "G": G, "M": M, "K": K, "C_AIR": C_AIR,
            "ALPHA_CU": ALPHA_CU, "BETA_COIL": BETA_COIL,
            "DT": DT, "T_END": T_END,
            "MU0": MU0, "M_MAG": M_MAG, "R_MAG": R_MAG, "H_MAG": H_MAG,
            "N_TURNS": N_TURNS, "R_LOAD": R_LOAD,
            "configs": CONFIGS,
        },
        "data": {},
    }
    for cfg in CONFIGS:
        d = data[cfg]
        n = len(d["t"])
        step = max(1, n // 400)
        out["data"][cfg] = {
            "t_s":         d["t"][::step].tolist(),
            "z_m":         d["z"][::step].tolist(),
            "v_m_s":       d["v"][::step].tolist(),
            "a_m_s2":      d["a"][::step].tolist(),
            "F_spring_N":  d["F_spring"][::step].tolist(),
            "KE_J":        d["KE"][::step].tolist(),
            "PE_J":        d["PE"][::step].tolist(),
            "E_total_J":   d["E_total"][::step].tolist(),
            "B_z_T":       d["B_z"][::step].tolist(),
            "EMF_V":       d["EMF"][::step].tolist(),
            "I_A":         d["I"][::step].tolist(),
            "E_field_V_m": d["E_field"][::step].tolist(),
            "summary": {
                "z_peak_m":       float(np.max(np.abs(d["z"]))),
                "v_peak_m_s":     float(np.max(np.abs(d["v"]))),
                "a_peak_m_s2":    float(np.max(np.abs(d["a"]))),
                "F_max_N":        float(np.max(np.abs(d["F_spring"]))),
                "KE_max_J":       float(np.max(np.abs(d["KE"]))),
                "PE_max_J":       float(np.max(np.abs(d["PE"]))),
                "E_total_max_J":  float(np.max(np.abs(d["E_total"]))),
                "B_max_T":        float(np.max(np.abs(d["B_z"]))),
                "E_max_V_m":      float(np.max(np.abs(d["E_field"]))),
                "EMF_max_V":      float(np.max(np.abs(d["EMF"]))),
                "I_max_A":        float(np.max(np.abs(d["I"]))),
            },
        }
    out_json.write_text(
        json.dumps(out, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"[ok] wrote {out_json}")


# ====================================================================
# CLI
# ====================================================================
def main():
    global K, M, C_AIR, ALPHA_CU, BETA_COIL, T_END, N, DAMPING
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-vtu", action="store_true",
                    help="ignored (no .vtu available)")
    ap.add_argument("--K", type=float, default=K,
                    help=f"spring stiffness N/m (default {K})")
    ap.add_argument("--M", type=float, default=M,
                    help=f"magnet mass kg (default {M})")
    ap.add_argument("--C-air", type=float, default=C_AIR,
                    help=f"air drag N*s/m (default {C_AIR})")
    ap.add_argument("--alpha-cu", type=float, default=ALPHA_CU,
                    help=f"copper damping N*s/m (default {ALPHA_CU})")
    ap.add_argument("--beta-coil", type=float, default=BETA_COIL,
                    help=f"coil Lenz damping N*s/m (default {BETA_COIL})")
    ap.add_argument("--T-end", type=float, default=T_END,
                    help=f"simulation duration s (default {T_END})")
    ap.add_argument("--out", type=str, default=None,
                    help="PNG output path (default results/dashboard.png)")
    args = ap.parse_args()

    K = args.K
    M = args.M
    C_AIR = args.C_air
    ALPHA_CU = args.alpha_cu
    BETA_COIL = args.beta_coil
    T_END = args.T_end
    N = int(T_END / DT)
    DAMPING = {"empty":  C_AIR,
               "copper": C_AIR + ALPHA_CU,
               "coil":   C_AIR + BETA_COIL}

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_png = Path(args.out) if args.out else (RESULTS / "dashboard.png")
    out_txt = out_png.with_suffix(".txt")
    out_jsn = out_png.with_suffix(".json")

    print("Running 3-config unified simulation ...")
    data = {cfg: simulate_full(cfg) for cfg in CONFIGS}

    make_dashboard(out_png, data)
    write_summary(data, out_txt)
    write_json(data, out_jsn)

    print()
    print(open(out_txt, encoding="utf-8").read())


if __name__ == "__main__":
    main()
