import yfinance as yf
import pandas as pd
import numpy as np
import time
import gspread
import os
from datetime import datetime
from ta.trend import PSARIndicator

# =========================
# SAFE FLOAT
# =========================
def safe_float(value):
    try:
        return float(value)
    except:
        return None


# =========================
# GOOGLE SHEET RETRY
# =========================
def open_sheet_with_retry(gc, name, retries=5):
    for i in range(retries):
        try:
            return gc.open(name)
        except Exception as e:
            print(f"Retry {i+1}: Google Sheet error:", e)
            time.sleep(5)
    raise Exception("❌ Failed to connect to Google Sheets")


# =========================
# NIFTY TREND (UNCHANGED)
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
# INDICATORS (UNCHANGED)
# =========================
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


# =========================
# FETCH DATA
# =========================
def get_data(symbol):
    try:
        ticker = symbol if symbol.endswith(".NS") else symbol + ".NS"

        df = yf.download(ticker, interval="1D", period="max", progress=False)

        if df is None or df.empty or len(df) < 200:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
        return df

    except:
        return None


# =========================
# BACKTEST (UNCHANGED)
# =========================
def backtest(df):

    close = df['Close']
    high = df['High']
    low = df['Low']

    rsi_val = rsi(close)
    macd, signal, hist = macd_pine(close)

    psar = PSARIndicator(high, low, close).psar()

    htf = df.resample('1D').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last'
    }).dropna()

    macd_htf, signal_htf, _ = macd_pine(htf['Close'])

    macd_htf = macd_htf.reindex(df.index, method='ffill')
    signal_htf = signal_htf.reindex(df.index, method='ffill')

    wins = losses = timeout = total = 0
    in_trade = False

    entry_price = 0
    entry_index = 0

    for i in range(100, len(df)):

        # ENTRY
        if not in_trade:
            if (45 <= rsi_val.iloc[i] <= 65) \
               and (rsi_val.iloc[i-1] < rsi_val.iloc[i]) \
               and (psar.iloc[i] < close.iloc[i]) \
               and (hist.iloc[i] > 0) \
               and (macd_htf.iloc[i] > signal_htf.iloc[i]) \
               and (macd_htf.iloc[i] > 0):

                in_trade = True
                entry_price = close.iloc[i]
                entry_index = i
                total += 1

        # EXIT
        elif in_trade:
            tp = entry_price * 1.25
            sl = entry_price * 0.85

            if high.iloc[i] >= tp and low.iloc[i] <= sl:
                losses += 1
                in_trade = False

            elif high.iloc[i] >= tp:
                wins += 1
                in_trade = False

            elif low.iloc[i] <= sl:
                losses += 1
                in_trade = False

            elif (i - entry_index) >= 100:
                timeout += 1
                in_trade = False

    win_rate = round((wins / total) * 100, 2) if total > 0 else 0

    return total, wins, losses, timeout, win_rate


# =========================
# SCANNER
# =========================
results = []

for stock in stocks:
    print(f"\n🔍 {stock}")

    df = get_data(stock)
    if df is None:
        continue

    total, wins, losses, timeout, win = backtest(df)

    if total > 0:
        results.append({
            "Stock": stock,
            "Total Trades": total,
            "Wins": wins,
            "Losses": losses,
            "Timeout": timeout,
            "Win%": win
        })

    time.sleep(0.2)


# =========================
# SAVE CSV
# =========================
if results:
    pd.DataFrame(results).to_csv("buy_candidates.csv", index=False)
    print("\n✅ CSV Saved")
else:
    print("\n🎯 No stocks found")


# =========================
# GOOGLE SHEET UPDATE (SAFE)
# =========================
try:
    gc = gspread.service_account(filename="credentials.json")

    sheet_obj = open_sheet_with_retry(gc, "PARABOLIC SAR")
    sheet = sheet_obj.worksheet("DaySAR")

    for row in results:
        sheet.append_row([
            row["Stock"],
            row["Total Trades"],
            row["Wins"],
            row["Losses"],
            row["Timeout"],
            row["Win%"],
            datetime.now().strftime("%Y-%m-%d")
        ])

    print("✅ Data pushed to Google Sheet")

except Exception as e:
    print("❌ Sheet Error:", e)
