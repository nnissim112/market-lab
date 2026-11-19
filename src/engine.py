"""Demo trading engine: 3 virtual accounts (risk 0.5% / 0.75% / 1% of equity, per מיקול),
entries only by the course rules, every trade journaled with the reason and a lesson."""
import json, os, time, datetime as dt
import pandas as pd
from data import candles
import smc

ROOT = os.environ.get("JOURNAL_DIR", "journal")
ACCOUNTS = {"A_0.5%": 0.005, "B_0.75%": 0.0075, "C_1%": 0.01}
START_EQUITY = 5000.0
MIN_RR = 2.0
FEES = {"crypto": 0.00055, "stock": 0.0002, "future": 0.0001}   # per side, APPROX
MAX_LEV = {"crypto": 10, "stock": 1, "future": 20}
UNIVERSE = [
    # symbol, kind, macro tf, timing tf, style
    ("BTC-USD", "crypto", "1d", "15m", "swing"),
    ("ETH-USD", "crypto", "1d", "15m", "swing"),
    ("SOL-USD", "crypto", "1d", "15m", "swing"),
    ("NQ=F", "future", "1h", "5m", "scalp"),
    ("ES=F", "future", "1h", "5m", "scalp"),
] + [(s, "stock", "1d", "15m", "swing") for s in
     ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "GOOGL",   # US most traded
      "TEVA", "NICE", "CHKP", "WIX", "ESLT", "MBLY"]]                   # Israeli, US-listed

def now():
    return dt.datetime.now(dt.timezone.utc)

def load():
    p = f"{ROOT}/state.json"
    if os.path.exists(p):
        return json.load(open(p))
    return {"accounts": {k: {"equity": START_EQUITY, "open": {}} for k in ACCOUNTS},
            "watch": {}, "trades": []}

def save(st):
    os.makedirs(ROOT, exist_ok=True)
    json.dump(st, open(f"{ROOT}/state.json", "w"), indent=1, default=str)

def quality(z, trigger):
    """Risk inside the account's band varies with the trade (ניסים, Q9): full-burn trigger 1
    with liquidity = full risk; weaker setups take less (מיקול: trigger 2 = reduced risk)."""
    q = 1.0 if trigger == 1 else 0.6
    if not (z.get("liquidity_above") or z.get("liquidity_below")):
        q -= 0.2
    return max(q, 0.5)

def size(equity, risk_pct, entry, stop, kind):
    """מחשבון המינוף: position = risk$ / stop%; leverage = position / cost (smallest possible)."""
    risk_usd = equity * risk_pct
    stop_pct = abs(entry - stop) / entry
    position = risk_usd / stop_pct
    lev = max(1.0, position / equity)
    if lev > MAX_LEV[kind]:                      # need too much leverage -> cut the risk
        position = equity * MAX_LEV[kind]
        risk_usd = position * stop_pct
        lev = MAX_LEV[kind]
    return position, risk_usd, round(lev, 2), stop_pct

def find_entry(sym, kind, mtf, ttf, style, st):
    """Entry timing (19.11): (1) throw into the interest zone (crypto: burn the WHOLE zone),
    (2) trade above the level - a bearish FVG from the drop is reclaimed = IFVG,
    (3) retest of the IFVG -> enter. Stop below the first low (iron). Target >= 1:2."""
    macro = candles(sym, kind, mtf, 300)
    if macro.empty:
        return None
    tr = smc.main_trend(macro)
    if tr.direction == "none":
        return None
    r = smc.retrace(tr, macro["close"].iloc[-1])
    if r < 0.25:          # not measured before a 0.25 correction
        return None
    zones = smc.interest_zones(macro, tr)
    if not zones:
        return None
    low_tf = candles(sym, kind, ttf, 300)
    if low_tf.empty or len(low_tf) < 30:
        return None
    used = st.setdefault("used_zones", [])
    for z in zones:
        zkey = f'{sym}:{z["dir"]}:{z["bottom"]:.6g}:{z["top"]:.6g}'
        if zkey in used:            # one shot per interest zone; a stopped-out zone is spent
            continue
        z["key"] = zkey
        if z["dir"] == "long":
            touched = low_tf[low_tf["low"] <= z["mid"]]
            if touched.empty:
                continue
            first_i = low_tf.index.get_loc(touched.index[0])
            seg = low_tf.iloc[first_i:]
            sweep_low = seg["low"].min()
            full_burn = sweep_low <= z["bottom"]
            if kind == "crypto" and not full_burn:
                continue                                      # respectful touch = manipulation
            trigger = 1 if full_burn else 2
            low_i = first_i + int(seg["low"].values.argmin())
            drop = low_tf.iloc[max(0, low_i - 20):low_i + 1]
            bears = [f for f in smc.fvgs(drop) if f["side"] == "bear"]
            if not bears:
                continue
            f = bears[-1]
            after = low_tf.iloc[low_i + 1:]
            reclaimed = after[after["close"] > f["top"]]
            if reclaimed.empty:
                continue
            rc_i = after.index.get_loc(reclaimed.index[0])
            post = after.iloc[rc_i + 1:]
            if post.empty:
                continue
            last = post.iloc[-1]
            retest = last["low"] <= f["top"] and last["close"] > f["bottom"]
            if not retest:
                continue
            entry, stop = float(last["close"]), float(sweep_low) * 0.999
            lows, highs = smc.swings(macro)
            targets = sorted(macro["high"].iloc[i] for i in highs if macro["high"].iloc[i] > entry)
            target = next((t for t in targets if (t - entry) >= MIN_RR * (entry - stop)), None)
            if target is None:
                target = tr.end if (tr.end - entry) >= MIN_RR * (entry - stop) else None
            if target is None:
                continue
            return dict(symbol=sym, kind=kind, style=style, side="long", entry=entry, stop=stop,
                        target=float(target), trigger=trigger, zone=z, trend=tr.__dict__,
                        retrace=round(r, 3), rr=round((target - entry) / (entry - stop), 2))
        else:   # short: mirror image (Invert Scale)
            touched = low_tf[low_tf["high"] >= z["mid"]]
            if touched.empty:
                continue
            first_i = low_tf.index.get_loc(touched.index[0])
            seg = low_tf.iloc[first_i:]
            sweep_high = seg["high"].max()
            full_burn = sweep_high >= z["top"]
            if kind == "crypto" and not full_burn:
                continue
            trigger = 1 if full_burn else 2
            hi_i = first_i + int(seg["high"].values.argmax())
            rise = low_tf.iloc[max(0, hi_i - 20):hi_i + 1]
            bulls = [f for f in smc.fvgs(rise) if f["side"] == "bull"]
            if not bulls:
                continue
            f = bulls[-1]
            after = low_tf.iloc[hi_i + 1:]
            broken = after[after["close"] < f["bottom"]]
            if broken.empty:
                continue
            post = after.iloc[after.index.get_loc(broken.index[0]) + 1:]
            if post.empty:
                continue
            last = post.iloc[-1]
            if not (last["high"] >= f["bottom"] and last["close"] < f["top"]):
                continue
            entry, stop = float(last["close"]), float(sweep_high) * 1.001
            lows, highs = smc.swings(macro)
            targets = sorted((macro["low"].iloc[i] for i in lows if macro["low"].iloc[i] < entry), reverse=True)
            target = next((t for t in targets if (entry - t) >= MIN_RR * (stop - entry)), None)
            if target is None:
                continue
            return dict(symbol=sym, kind=kind, style=style, side="short", entry=entry, stop=stop,
                        target=float(target), trigger=trigger, zone=z, trend=tr.__dict__,
                        retrace=round(r, 3), rr=round((entry - target) / (stop - entry), 2))
    return None

def open_trade(st, setup):
    st.setdefault("used_zones", []).append(setup["zone"]["key"])
    for name, base in ACCOUNTS.items():
        acc = st["accounts"][name]
        if setup["symbol"] in acc["open"]:
            continue
        risk_pct = base * quality(setup["zone"], setup["trigger"])
        pos, risk_usd, lev, stop_pct = size(acc["equity"], risk_pct, setup["entry"], setup["stop"], setup["kind"])
        acc["open"][setup["symbol"]] = {**setup, "account": name, "opened": str(now()), "position": pos,
                                        "risk_usd": round(risk_usd, 2), "risk_pct": round(risk_pct * 100, 3),
                                        "leverage": lev, "stop_pct": round(stop_pct * 100, 3)}

def manage(st):
    for name, acc in st["accounts"].items():
        for sym, t in list(acc["open"].items()):
            df = candles(sym, t["kind"], "5m", 50)
            if df.empty:
                continue
            df = df[df.index > pd.Timestamp(t["opened"])]
            exit_px, why = None, None
            for _, b in df.iterrows():
                if t["side"] == "long":
                    if b["low"] <= t["stop"]: exit_px, why = t["stop"], "stop"; break
                    if b["high"] >= t["target"]: exit_px, why = t["target"], "target"; break
                else:
                    if b["high"] >= t["stop"]: exit_px, why = t["stop"], "stop"; break
                    if b["low"] <= t["target"]: exit_px, why = t["target"], "target"; break
            if exit_px is None:
                continue
            move = (exit_px - t["entry"]) / t["entry"] * (1 if t["side"] == "long" else -1)
            fee = 2 * FEES[t["kind"]] * t["position"]
            pnl = t["position"] * move - fee
            acc["equity"] = round(acc["equity"] + pnl, 2)
            st["trades"].append({**t, "closed": str(now()), "exit": exit_px, "result": why,
                                 "pnl": round(pnl, 2), "fees": round(fee, 2), "equity_after": acc["equity"]})
            del acc["open"][sym]

def run(minutes=355, every=300, styles=("swing", "scalp")):
    st = load()
    end = time.time() + minutes * 60
    while True:
        manage(st)
        for sym, kind, mtf, ttf, style in UNIVERSE:
            if style not in styles:
                continue
            if all(sym in a["open"] for a in st["accounts"].values()):
                continue
            try:
                s = find_entry(sym, kind, mtf, ttf, style, st)
            except Exception as e:
                print("scan error", sym, e); s = None
            if s:
                print("ENTRY", s["symbol"], s["side"], s["entry"], s["rr"])
                open_trade(st, s)
        st["last_run"] = str(now())
        save(st)
        if time.time() + every > end:
            break
        time.sleep(every)

if __name__ == "__main__":
    import sys
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 355
    styles = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("swing", "scalp")
    run(m, 300 if m > 10 else 1, styles)
