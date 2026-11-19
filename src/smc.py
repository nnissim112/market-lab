"""Chart reading rules from the WISE / מיקול course, as code.
Approximations are marked APPROX so the weekly review can refine them."""
from dataclasses import dataclass
import pandas as pd

def swings(df, k=3):
    """V-shaped lows / Λ highs: a bar lower (higher) than k bars on each side (APPROX of 'V shape')."""
    lows, highs = [], []
    lo, hi = df["low"].values, df["high"].values
    for i in range(k, len(df) - k):
        if lo[i] == min(lo[i - k:i + k + 1]):
            lows.append(i)
        if hi[i] == max(hi[i - k:i + k + 1]):
            highs.append(i)
    return lows, highs

@dataclass
class Trend:
    direction: str      # "up" / "down" / "none"
    start: float        # the extreme that created the trend (fib 1)
    end: float          # the extreme the trend reached (fib 0)
    start_i: int
    end_i: int

def main_trend(df):
    """Four questions, right to left (module 06). Price -> the extreme it came from as a trend
    -> the opposite extreme that created it. More rise than fall = uptrend in correction."""
    if len(df) < 30:
        return Trend("none", 0, 0, 0, 0)
    price = df["close"].iloc[-1]
    hi_i = int(df["high"].values.argmax()); lo_i = int(df["low"].values.argmin())
    if hi_i > lo_i:      # last extreme is the high: uptrend from the low before it
        start_i, end_i = int(df["low"].values[:hi_i + 1].argmin()), hi_i
        start, end = df["low"].iloc[start_i], df["high"].iloc[end_i]
        rise, fall = end - start, end - price
        d = "up" if rise > fall else "down"
    else:
        start_i, end_i = int(df["high"].values[:lo_i + 1].argmax()), lo_i
        start, end = df["high"].iloc[start_i], df["low"].iloc[end_i]
        fall, rise = start - end, price - end
        d = "down" if fall > rise else "up"
    # all-time high / low: no correction to analyse (module 06)
    if end_i >= len(df) - 2:
        d = "none"
    return Trend(d, float(start), float(end), start_i, end_i)

def fib_level(tr, v):
    """Trend fib: 1 = start, 0 = end."""
    return tr.end + (tr.start - tr.end) * v

def retrace(tr, price):
    span = tr.start - tr.end
    return (price - tr.end) / span if span else 0.0

def fvgs(df, start=0):
    """3-candle imbalance: rectangle from wick of candle 1 to wick of candle 3 (מיקול 2)."""
    out = []
    h, l = df["high"].values, df["low"].values
    for i in range(max(start, 1), len(df) - 1):
        if l[i + 1] > h[i - 1]:
            out.append({"i": i, "side": "bull", "bottom": h[i - 1], "top": l[i + 1]})
        elif h[i + 1] < l[i - 1]:
            out.append({"i": i, "side": "bear", "bottom": h[i + 1], "top": l[i - 1]})
    for z in out:
        z["mid"] = (z["top"] + z["bottom"]) / 2
    return out

def interest_zones(df, tr):
    """Interest zone = combination of indications: discount (<=0.705 in uptrend, >=0.705 in
    downtrend) + an FVG there + liquidity (a swing low/high above it for longs/below for shorts)."""
    zones = []
    if tr.direction == "none":
        return zones
    lvl705 = fib_level(tr, 0.705)
    lows, highs = swings(df)
    lo_i, hi_i = sorted((tr.start_i, tr.end_i))
    for z in [f for f in fvgs(df, lo_i) if f["i"] <= hi_i]:   # FVGs inside the trend leg
        if tr.direction == "up" and z["side"] == "bull" and z["top"] <= lvl705 and z["bottom"] > tr.start:
            liq = any(df["low"].iloc[i] > z["top"] for i in lows if i > z["i"])
            zones.append({**z, "dir": "long", "liquidity_above": liq})
        if tr.direction == "down" and z["side"] == "bear" and z["bottom"] >= lvl705 and z["top"] < tr.start:
            liq = any(df["high"].iloc[i] < z["bottom"] for i in highs if i > z["i"])
            zones.append({**z, "dir": "short", "liquidity_below": liq})
    return zones
