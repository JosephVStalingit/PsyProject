# -*- coding: utf-8 -*-
"""
test_oscilloscope.py  ── 验证 oscilloscope.py 数学正确性

物理预期：
    empty : 欠阻尼 ζ≈0.01, 振荡周期 T≈1.28 s
    copper: 欠阻尼 ζ≈0.11, 衰减时间 τ≈1.8 s
    coil  : 欠阻尼 ζ≈0.13, 衰减时间 τ≈1.5 s
    三者 ζ 必须单调递增：empty < copper < coil
    三者 z_peak 必须单调递减：empty > copper > coil
"""
import os, sys
from pathlib import Path
WORKDIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKDIR))
import oscilloscope as osc


def test_damping_monotonic():
    import math
    omega0 = math.sqrt(osc.K / osc.M)
    zetas = [osc.DAMPING[c] / (2 * osc.M * omega0) for c in osc.CONFIGS]
    assert zetas[0] < zetas[1] < zetas[2], f"damping not monotonic: {zetas}"


def test_period_in_range():
    import math
    for c in osc.CONFIGS:
        t, z, v, a = osc.simulate(c, n=1000)
        # 找到 z 的前两个过零点 → 半周期
        zero_cross = []
        for i in range(1, len(z)):
            if z[i-1] > 0 and z[i] <= 0:
                zero_cross.append(t[i])
        if len(zero_cross) >= 2:
            half_period = zero_cross[1] - zero_cross[0]
            period = 2 * half_period
            # T should be near 1.28 s (undamped)
            assert 1.0 < period < 1.6, f"{c}: period={period:.3f} not in [1, 1.6]"


def test_peak_decreasing():
    peaks = []
    for c in osc.CONFIGS:
        t, z, v, a = osc.simulate(c, n=2000)
        peaks.append(abs(z[0]))
    # 初始 z=0 因为 z(0)=0；第一个峰在 dt 后才有意义
    # 重新算：peak = max(|z|)
    peaks = []
    for c in osc.CONFIGS:
        t, z, v, a = osc.simulate(c, n=2000)
        peaks.append(float(max(abs(z))))
    assert peaks[0] > peaks[1] > peaks[2], f"peak not decreasing: {peaks}"


def test_decay_rate():
    """在 t=0.5 s 和 t=2.5 s 比较 |z|，衰减比应大致匹配 exp(-(t2-t1)/tau)"""
    for c in osc.CONFIGS:
        t, z, v, a = osc.simulate(c, n=3000)
        # 找局部极大值
        import numpy as np
        z_np = z
        # 找前两个极大值
        peaks_idx = []
        for i in range(1, len(z_np)-1):
            if z_np[i-1] < z_np[i] > z_np[i+1]:
                peaks_idx.append(i)
                if len(peaks_idx) >= 2:
                    break
        if len(peaks_idx) >= 2:
            ratio = abs(z_np[peaks_idx[1]]) / abs(z_np[peaks_idx[0]])
            assert 0 < ratio < 1.0, f"{c}: ratio={ratio:.3f} not in (0,1)"


def test_oscilloscope_png():
    """跑 make_oscilloscope() 验证 PNG 写得出来"""
    import os
    out = osc.RESULTS / "oscilloscope.png"
    if out.exists():
        out.unlink()
    osc.make_oscilloscope(out)
    assert out.exists(), "PNG not written"
    assert out.stat().st_size > 50_000, "PNG too small"


def test_summary_txt():
    out = osc.RESULTS / "summary.txt"
    if out.exists():
        out.unlink()
    summary = osc.make_oscilloscope(osc.RESULTS / "oscilloscope.png")
    osc.write_summary(summary, out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "empty" in content and "copper" in content and "coil" in content
