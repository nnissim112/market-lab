"""Chart for each closed trade: candles + entry / stop / target (for the Saturday summary)."""
import json, os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from data import candles
ROOT = os.environ.get("JOURNAL_DIR", "journal")

def chart(t, out):
    df = candles(t["symbol"], t["kind"], "15m", 200)
    if df.empty: return
    df = df[df.index >= pd.Timestamp(t["opened"]) - pd.Timedelta(hours=24)]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for ts, b in df.iterrows():
        c = "#2e7d32" if b["close"] >= b["open"] else "#c62828"
        ax.vlines(ts, b["low"], b["high"], color=c, lw=0.8)
        ax.vlines(ts, min(b["open"], b["close"]), max(b["open"], b["close"]), color=c, lw=3)
    for y, c, lab in ((t["entry"], "#1565c0", "entry"), (t["stop"], "#c62828", "stop"), (t["target"], "#2e7d32", "target")):
        ax.axhline(y, color=c, ls="--", lw=1); ax.text(df.index[0], y, f" {lab} {y:,.2f}", color=c, va="bottom")
    ax.axvline(pd.Timestamp(t["opened"]), color="#555", lw=0.8)
    ax.set_title(f'{t["symbol"]} {t["side"]} | {t["result"]} | PnL {t["pnl"]:+.2f}$ | {t["account"]}')
    fig.tight_layout(); fig.savefig(out, dpi=110); plt.close(fig)

if __name__ == "__main__":
    st = json.load(open(f"{ROOT}/state.json"))
    os.makedirs(f"{ROOT}/charts", exist_ok=True)
    for k, t in enumerate(st["trades"]):
        out = f'{ROOT}/charts/{t["closed"][:10]}_{t["symbol"]}_{t["account"]}_{k}.png'
        if not os.path.exists(out):
            chart(t, out)
