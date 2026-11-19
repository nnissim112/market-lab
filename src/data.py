"""Market data from free public sources (no accounts).
Crypto: Coinbase Exchange public candles. Stocks / futures: Yahoo via yfinance."""
import time, json, urllib.request
import pandas as pd

CB_GRAN = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}

def _cb(symbol, tf, n=300):
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={CB_GRAN[tf]}"
    req = urllib.request.Request(url, headers={"User-Agent": "short-term-demo"})
    rows = json.loads(urllib.request.urlopen(req, timeout=20).read())
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    df["t"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df.sort_values("t").set_index("t")[["open", "high", "low", "close", "volume"]].tail(n)

def _yf(symbol, tf, n=300):
    import yfinance as yf
    period = {"5m": "5d", "15m": "30d", "1h": "180d", "1d": "5y", "1wk": "15y"}[tf]
    df = yf.download(symbol, period=period, interval=tf, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df.tail(n)

def candles(symbol, kind, tf, n=300, retries=3):
    for i in range(retries):
        try:
            return _cb(symbol, tf, n) if kind == "crypto" else _yf(symbol, tf, n)
        except Exception as e:  # network hiccup
            last = e
            time.sleep(3 * (i + 1))
    print(f"data error {symbol} {tf}: {last}")
    return pd.DataFrame()
