import yfinance as yf
import pandas as pd
import numpy as np
import time

# =========================
# NIFTY TREND (DO NOT CHANGE)
# =========================
def get_nifty_trend():
    try:
        df = yf.download("^NSEI", interval="1d", period="1y", progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        sma_100 = close.rolling(100).mean()

        if close.iloc[-1] < sma_100.iloc[-1]:
            print("🟢 Using DownTrend")
            return "DownTrend"
        else:
            print("🔴 Using Uptrend")
            return "Uptrend"

    except Exception as e:
        print("❌ NIFTY Error:", e)
        return "DownTrend"


# =========================
# LOAD STOCKS
# =========================
list_name = get_nifty_trend()

try:
    with open(list_name + ".txt") as f:
        stocks = [line.strip().upper() for line in f if line.strip()]
except:
    print("❌ Stock list file missing")
    exit()

print(f"📊 Loaded {len(stocks)} stocks")


# =========================
# INDICATORS
# =========================

# ✅ FIXED RSI (WILDER / EMA like Pine)
def rsi(series, length=14):
    delta = series.diff()

    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain, index=series.index)
    loss = pd.Series(loss, index=series.index)

    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def macd_pine(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line

    return macd_line, signal_line, hist


def psar(high, low, close, step=0.02, max_step=0.2):
    bull = True
    af = step
    ep = low.iloc[0]
    psar_values = []

    for i in range(len(close)):
        if i == 0:
            psar_values.append(close.iloc[0])
            continue

        prev_psar = psar_values[-1]

        if bull:
            psar_val = prev_psar + af * (ep - prev_psar)
            if low.iloc[i] < psar_val:
                bull = False
                psar_val = ep
                af = step
                ep = low.iloc[i]
        else:
            psar_val = prev_psar + af * (ep - prev_psar)
            if high.iloc[i] > psar_val:
                bull = True
                psar_val = ep
                af = step
                ep = high.iloc[i]

        if bull:
            ep = max(ep, high.iloc[i])
        else:
            ep = min(ep, low.iloc[i])

        af = min(af + step, max_step)
        psar_values.append(psar_val)

    return pd.Series(psar_values, index=close.index)


# =========================
# FETCH DATA
# =========================
def get_data(symbol):
    try:
        ticker = symbol if symbol.endswith(".NS") else symbol + ".NS"

        df = yf.download(ticker, interval="1d", period="max", progress=False)

        if df is None or df.empty or len(df) < 200:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()

        return df, df['Close'], df['High'], df['Low']

    except:
        return None


# =========================
# BACKTEST
# =========================
def backtest(df, close, high, low):
    rsi_val = rsi(close)
    macd, signal, hist = macd_pine(close)
    sar = psar(high, low, close)

    # ✅ HTF FIXED → DAILY (same as Pine)
    htf = df.copy()
    macd_htf, signal_htf, _ = macd_pine(htf['Close'])

    macd_htf = macd_htf.reindex(df.index, method='ffill')
    signal_htf = signal_htf.reindex(df.index, method='ffill')

    wins = losses = timeout = total = 0
    i = 100

    while i < len(df) - 100:

        if (45 <= rsi_val.iloc[i] <= 65) \
           and (rsi_val.iloc[i-1] < rsi_val.iloc[i]) \
           and (sar.iloc[i] < close.iloc[i]) \
           and (hist.iloc[i] > 0) \
           and (macd_htf.iloc[i] > signal_htf.iloc[i] > 0):

            entry = close.iloc[i]
            target = entry * 1.25
            stop = entry * 0.85

            j_end = min(i + 100, len(df)-1)
            closed = False

            for j in range(i+1, j_end):
                if high.iloc[j] >= target:
                    wins += 1
                    closed = True
                    break
                elif low.iloc[j] <= stop:
                    losses += 1
                    closed = True
                    break

            if not closed:
                timeout += 1

            total += 1
            i = j_end
        else:
            i += 1

    win_rate = round((wins / total) * 100, 2) if total > 0 else 0
    return total, wins, losses, timeout, win_rate


# =========================
# SCANNER
# =========================
results = []

for stock in stocks:
    print(f"\n🔍 {stock}")

    data = get_data(stock)
    if data is None:
        continue

    df, close, high, low = data

    rsi_val = rsi(close)
    macd, signal, hist = macd_pine(close)
    sar = psar(high, low, close)

    # ✅ HTF FIXED → DAILY
    htf = df.copy()
    macd_htf, signal_htf, _ = macd_pine(htf['Close'])

    macd_htf = macd_htf.reindex(df.index, method='ffill')
    signal_htf = signal_htf.reindex(df.index, method='ffill')

    if (45 <= rsi_val.iloc[-1] <= 65) \
       and (rsi_val.iloc[-2] < rsi_val.iloc[-1]) \
       and (sar.iloc[-1] < close.iloc[-1]) \
       and (hist.iloc[-1] > 0) \
       and (macd_htf.iloc[-1] > signal_htf.iloc[-1] > 0):

        print("✅ SELECTED")

        total, wins, losses, timeout, win = backtest(df, close, high, low)

        results.append({
            "Stock": stock,
            "Price": round(close.iloc[-1], 2),
            "Total Trades": total,
            "Wins": wins,
            "Losses": losses,
            "Timeout": timeout,
            "Win%": win
        })

    else:
        print("❌ Not matched")

    time.sleep(0.2)


# =========================
# SAVE CSV
# =========================
if results:
    pd.DataFrame(results).to_csv("buy_candidates.csv", index=False)
    print("\n✅ CSV Saved")
else:
    print("\n🎯 No stocks found")
