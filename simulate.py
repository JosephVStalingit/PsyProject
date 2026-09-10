"""
simulate.py  --  Unified driver driven by config.json

Each block in config.json defines ONE simulation curve.  Each block
is fully self-describing: coil turns, material, release height, spring
stiffness, air drag, etc.  Results: 1 dashboard PNG, 1 ASCII summary,
1 JSON dump, all keyed by block name.

Example config.json (two blocks; one coil + one empty):

{
  "runs": {
    "coil_50t_aluminum": {
      "comment":      "50 turn copper coil, no air drag, aluminium magnet",
      "magnet": {
        "material":       "NdFeB",     // label only
        "radius_m":       0.015,
        "height_m":       0.030,
        "mass_kg":        0.5,
        "M_z_Am":        -1.2e6       // magnetisation z component
      },
      "coil": {
        "enabled":        true,
        "turns":          50,
        "wire_area_m2":   5.0e-7,
        "wire_cond_Sm":   5.96e7,
        "load_R_ohm":    10.0
      },
      "spring": {
        "k_Npm":         12.0,        // spring stiffness
        "natural_z_m":    0.075,       // equilibrium position
        "release_z_m":    0.075        // initial magnet position
      },
      "air_drag": {
        "enabled":        false,
        "c_Ns_per_m":     0.05
      },
      "simulation": {
        "dt_s":          0.001,
        "t_end_s":       3.0,
        "g_mps2":        9.81
      }
    },
    "no_coil_vacuum": {
      "comment":      "no coil, vacuum, spring only",
      "magnet": {"material":"NdFeB","radius_m":0.015,"height_m":0.030,
                "mass_kg":0.5,"M_z_Am":-1.2e6},
      "coil":   {"enabled":false,"turns":0,"wire_area_m2":0,
                  "wire_cond_Sm":0,"load_R_ohm":1e9},
      "spring": {"k_Npm":12.0,"natural_z_m":0.075,"release_z_m":0.075},
      "air_drag": {"enabled":false,"c_Ns_per_m":0.0},
      "simulation": {"dt_s":0.001,"t_end_s":3.0,"g_mps2":9.81}
    }
  }
}

Usage:
    python simulate.py                                # default config.json
    python simulate.py --config my.json --out out/    # custom I/O
    python simulate.py --runs coil_50t_aluminum       # one specific run
"""

from __future__ import annotations
import os, sys, json, math, argparse
from pathlib import Path
import numpy as np

WORKDIR = Path(__file__).parent.resolve()
MU0 = 4.0 * math.pi * 1e-7

# Default config embedded as fallback
DEFAULT_CONFIG = {
    "runs": {
        "coil_50t": {
            "comment": "50 turn coil, no air drag",
            "magnet": {"material": "NdFeB", "radius_m": 0.015,
                       "height_m": 0.030, "mass_kg": 0.5,
                       "M_z_Am": -1.2e6},
            "coil":   {"enabled": True, "turns": 50,
                       "wire_area_m2": 5.0e-7,
                       "wire_cond_Sm": 5.96e7,
                       "load_R_ohm": 10.0},
            "spring": {"k_Npm": 12.0, "natural_z_m": 0.075,
                       "release_z_m": 0.075},
            "air_drag": {"enabled": False, "c_Ns_per_m": 0.05},
            "simulation": {"dt_s": 0.001, "t_end_s": 3.0, "g_mps2": 9.81}
        },
        "no_coil_vacuum": {
            "comment": "no coil, vacuum, spring only",
            "magnet": {"material": "NdFeB", "radius_m": 0.015,
                       "height_m": 0.030, "mass_kg": 0.5,
                       "M_z_Am": -1.2e6},
            "coil":   {"enabled": False, "turns": 0,
                       "wire_area_m2": 0.0,
                       "wire_cond_Sm": 0.0,
                       "load_R_ohm": 1e9},
            "spring": {"k_Npm": 12.0, "natural_z_m": 0.075,
                       "release_z_m": 0.075},
            "air_drag": {"enabled": False, "c_Ns_per_m": 0.0},
            "simulation": {"dt_s": 0.001, "t_end_s": 3.0, "g_mps2": 9.81}
        }
    }
}



# ====================================================================
# Analytical B field of a uniformly-magnetised cylinder (on axis)
# ====================================================================
def B_z_axis(zp, M, R, H):
    """On-axis B_z of a uniformly magnetised cylinder.
    zp : distance from magnet centre (m)
    M  : magnetisation (A/m)
    R  : radius (m)
    H  : half-height (m)
    """
    r2 = R ** 2
    return (MU0 / 2.0) * M * (
        (zp + H) / math.sqrt(r2 + (zp + H)**2)
        - (zp - H) / math.sqrt(r2 + (zp - H)**2))


def flux_in_coil(z_mag, M, R, H, coil_z0, coil_z1, coil_R_out, coil_R_in):
    """Flux captured by the coil block (A_coil = pi*(R_out^2 - R_in^2)).
    Returns flux per turn (Wb)."""
    n = 21
    zs = [coil_z0 + (coil_z1 - coil_z0) * i / (n - 1) for i in range(n)]
    avg_B = sum(B_z_axis(zz - z_mag, M, R, H) for zz in zs) / n
    A_coil = math.pi * (coil_R_out**2 - coil_R_in**2)
    return avg_B * A_coil


# ====================================================================
# Simulate one run (ODE + B field + EMF/I)
# ====================================================================
def simulate_one(cfg: dict):
    """Run a single configuration; return (t, z, v, a, B, EMF, I, E_field)
       all aligned numpy arrays."""
    mag = cfg["magnet"]
    coil = cfg["coil"]
    spr = cfg["spring"]
    drag = cfg["air_drag"]
    sim = cfg["simulation"]

    M = mag["mass_kg"]
    K = spr["k_Npm"]
    g = sim["g_mps2"]
    dt = sim["dt_s"]
    t_end = sim["t_end_s"]
    n = int(t_end / dt)

    z0 = spr["release_z_m"] - spr["natural_z_m"]
    c = drag["c_Ns_per_m"] if drag["enabled"] else 0.0

    z = np.zeros(n + 1); v = np.zeros(n + 1); a = np.zeros(n + 1)
    z[0] = z0; v[0] = 0.0
    t = np.arange(0, (n + 1) * dt, dt)

    def f(z, v):
        return (v, (M * g - K * z - c * v) / M)
    for i in range(n):
        k1z, k1v = f(z[i], v[i])
        k2z, k2v = f(z[i] + 0.5*dt*k1z, v[i] + 0.5*dt*k1v)
        k3z, k3v = f(z[i] + 0.5*dt*k2z, v[i] + 0.5*dt*k2v)
        k4z, k4v = f(z[i] + dt*k3z, v[i] + dt*k3v)
        z[i+1] = z[i] + dt/6.0 * (k1z + 2*k2z + 2*k3z + k4z)
        v[i+1] = v[i] + dt/6.0 * (k1v + 2*k2v + 2*k3v + k4v)
        a[i+1] = (M*g - K*z[i+1] - c*v[i+1]) / M

    # Field on axis (world z = ODE z + natural_z)
    z_world = z + spr["natural_z_m"]
    B = np.array([B_z_axis(zi, mag["M_z_Am"], mag["radius_m"], mag["height_m"]/2)
                  for zi in z_world])

    # EMF / I from coil flux linkage (or zero if no coil)
    if coil["enabled"]:
        N = coil["turns"]
        R = coil["load_R_ohm"]
        Phi = np.array([flux_in_coil(zw, mag["M_z_Am"], mag["radius_m"],
                                       mag["height_m"]/2,
                                       -0.02, +0.02, 0.025, 0.020) * N
                        for zw in z_world])
        dt_arr = np.gradient(t)
        EMF = -np.gradient(Phi) / dt_arr
        I = EMF / R
        E_field = np.abs(I) * 1.68e-8 / coil["wire_area_m2"]
    else:
        EMF = np.zeros_like(z)
        I = np.zeros_like(z)
        E_field = np.zeros_like(z)

    return {
        "t": t, "z": z, "v": v, "a": a,
        "z_world": z_world, "B_z": B,
        "EMF": EMF, "I": I, "E_field": E_field,
        "F_spring": -K * z,
        "KE": 0.5 * M * v**2,
        "PE": 0.5 * K * z**2,
        "E_total": 0.5 * M * v**2 + 0.5 * K * z**2,
        "summary": {
            "z_peak_m":  float(np.max(np.abs(z))),
            "v_peak_m_s": float(np.max(np.abs(v))),
            "a_peak_m_s2": float(np.max(np.abs(a))),
            "B_max_T":  float(np.max(np.abs(B))),
            "EMF_max_V": float(np.max(np.abs(EMF))),
            "I_max_A":   float(np.max(np.abs(I))),
            "E_max_V_m": float(np.max(np.abs(E_field))),
            "KE_max_J": float(np.max(np.abs(0.5*M*v**2))),
            "PE_max_J": float(np.max(np.abs(0.5*K*z**2))),
            "zeta":     c / (2*M*math.sqrt(K/M)) if M > 0 and K > 0 else 0.0,
            "tau_s":    2*M/(c) if c > 0 else float("inf"),
        }
    }


# ====================================================================
# Plotting + output
# ====================================================================
CHANNELS = [
    ("z",         "位移 z(t)",         "m"),
    ("v",         "速度 v(t)",         "m/s"),
    ("a",         "加速度 a(t)",       "m/s^2"),
    ("F_spring",  "弹簧力 F_s(t)",     "N"),
    ("KE",        "动能 KE(t)",        "J"),
    ("PE",        "势能 PE(t)",        "J"),
    ("E_total",   "总能量 E(t)",       "J"),
    ("B_z",       "磁通密度 B_z(t)",   "T"),
    ("EMF",       "感应电动势 EMF(t)", "V"),
    ("I",         "感应电流 I(t)",     "A"),
]

_PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]


def plot_dashboard(results, run_names, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for cand in ["SimHei", "Microsoft YaHei", "Noto Sans CJK SC",
                 "Arial Unicode MS", "PingFang SC", "WenQuanYi Zen Hei",
                 "Source Han Sans CN"]:
        if cand in {f.name for f in font_manager.fontManager.ttflist}:
            plt.rcParams["font.sans-serif"] = [cand]
            break
    plt.rcParams["axes.unicode_minus"] = False

    ncols = len(CHANNELS)
    fig, axes = plt.subplots(1, ncols, figsize=(30, 5.5), sharex=True)
    for c, (key, title, unit) in enumerate(CHANNELS):
        ax = axes[c]
        for i, name in enumerate(run_names):
            d = results[name]
            color = _PALETTE[i % len(_PALETTE)]
            ax.plot(d["t"], d[key], color=color, lw=1.6, label=name)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("t (s)")
        ax.set_ylabel(unit)
        ax.grid(True, alpha=0.3)
        ax.axhline(0, color="k", lw=0.4, alpha=0.3)
        if c == 0:
            ax.legend(fontsize=8, loc="best")

    fig.suptitle("UNIFIED Dashboard - " +
                 f"{len(run_names)} runs from config.json\n" +
                 "E-field + B-field + simple-harmonic dynamics",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote {out_png}")


def write_summary(results, cfg, run_names, out_txt):
    lines = []
    lines.append("=" * 110)
    lines.append(f" UNIFIED summary  -  {len(run_names)} runs")
    lines.append("=" * 110)
    lines.append(
        f"{'name':<22} {'coil':>5} {'R_load':>10} {'k(N/m)':>9} "
        f"{'M(kg)':>7} {'c(N*s/m)':>10} {'z_peak':>9} {'v_peak':>9} "
        f"{'B_max':>10} {'EMF_max':>10} {'I_max':>11} {'tau(s)':>8}"
    )
    lines.append("-" * 110)
    for name in run_names:
        d = results[name]
        s = d["summary"]
        c = cfg[name]["coil"]
        spr = cfg[name]["spring"]
        drag = cfg[name]["air_drag"]
        r_str = "inf" if math.isinf(c["load_R_ohm"]) else f"{c['load_R_ohm']:.2e}"
        coil_str = "yes" if c["enabled"] else "no"
        c_drag = drag["c_Ns_per_m"] if drag["enabled"] else 0.0
        tau_str = "inf" if math.isinf(s["tau_s"]) else f"{s['tau_s']:.3f}"
        lines.append(
            f"{name:<22} {coil_str:>5} {r_str:>10} {spr['k_Npm']:>9.2f} "
            f"{cfg[name]['magnet']['mass_kg']:>7.3f} {c_drag:>10.4f} "
            f"{s['z_peak_m']:>9.4f} {s['v_peak_m_s']:>9.4f} "
            f"{s['B_max_T']:>10.3e} {s['EMF_max_V']:>10.3e} "
            f"{s['I_max_A']:>11.3e} {tau_str:>8}"
        )
    lines.append("-" * 110)
    lines.append("")
    lines.append("Channels:")
    for line in [
        "  z         位移       (m)        v       速度         (m/s)",
        "  a         加速度     (m/s^2)    F_s     弹簧力       (N)",
        "  KE        动能       (J)        PE      势能         (J)",
        "  E_total   总能量     (J)        B_z     磁通密度     (T)",
        "  EMF       感应电动势 (V)        I       感应电流     (A)",
    ]:
        lines.append(line)
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_txt}")


def write_json(results, cfg, run_names, out_json):
    out = {"metadata": {"n_runs": len(run_names), "MU0": MU0,
                        "runs": run_names},
           "config": cfg, "results": {}}
    for name in run_names:
        d = results[name]
        n = len(d["t"])
        step = max(1, n // 400)
        out["results"][name] = {
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
            "summary": d["summary"],
        }
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"[ok] wrote {out_json}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--out", default="results")
    ap.add_argument("--runs", default=None,
                    help="comma-separated run names to simulate (default: all)")
    ap.add_argument("--write-default", action="store_true",
                    help="write a sample config.json next to this script and exit")
    args = ap.parse_args()

    if args.write_default:
        out_cfg = WORKDIR / "config.json"
        if out_cfg.exists():
            print(f"config.json already exists at {out_cfg}")
        else:
            out_cfg.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"[ok] wrote {out_cfg}")
        return

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = WORKDIR / cfg_path
    if not cfg_path.exists():
        print(f"config not found: {cfg_path}")
        print("run with --write-default to create a sample")
        sys.exit(1)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    runs = cfg["runs"]

    if args.runs:
        wanted = [r.strip() for r in args.runs.split(",")]
        runs = {k: v for k, v in runs.items() if k in wanted}
        missing = set(wanted) - set(runs.keys())
        if missing:
            print(f"WARN: missing runs in config: {missing}")
    run_names = list(runs.keys())
    print(f"Simulating {len(run_names)} run(s): {run_names}")

    out_dir = WORKDIR / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {name: simulate_one(cfg_block)
               for name, cfg_block in runs.items()}

    plot_dashboard(results, run_names, out_dir / "dashboard.png")
    write_summary(results, runs, run_names, out_dir / "summary.txt")
    write_json(results, runs, run_names, out_dir / "data.json")
    print("[done]")


if __name__ == "__main__":
    main()
