import yfinance as yf
import pandas as pd
import numpy as np
import time
import gspread
from datetime import datetime
from ta.trend import PSARIndicator
from ta.momentum import RSIIndicator

# =========================
# GOOGLE SHEET RETRY
# =========================
import os
import json
import gspread

creds_dict = {
    "type": os.environ["type"],
    "project_id": os.environ["project_id"],
    "private_key_id": os.environ["private_key_id"],
    "private_key": os.environ["private_key"].replace("\\n", "\n"),
    "client_email": os.environ["client_email"],
    "client_id": os.environ["client_id"],
    "auth_uri": os.environ["auth_uri"],
    "token_uri": os.environ["token_uri"],
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ["client_x509_cert_url"],
    "universe_domain": os.environ.get("universe_domain", "googleapis.com")
}

gc = gspread.service_account_from_dict(creds_dict)

# =========================
# NIFTY TREND
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

    except:
        return "DownTrend"


# =========================
# HTF FILTER (WEEKLY MACD)
# =========================
def get_htf_trend(symbol):
    try:
        ticker = symbol if symbol.endswith(".NS") else symbol + ".NS"

        df = yf.download(ticker, interval="1wk", period="5y", progress=False)

        if df is None or df.empty or len(df) < 50:
            return False

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()

        macd = ema_fast - ema_slow
        signal = macd.ewm(span=9, adjust=False).mean()

        return macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-1] > 0

    except:
        return False


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
# MACD FUNCTION
# =========================
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

        df = yf.download(ticker, interval="1d", period="1y", progress=False)

        if df is None or df.empty or len(df) < 100:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
        return df

    except:
        return None


# =========================
# SCANNER (LIVE SIGNAL)
# =========================
results = []

for stock in stocks:
    print(f"\n🔍 {stock}")

    df = get_data(stock)
    if df is None:
        continue

    # HTF FILTER
    if not get_htf_trend(stock):
        print("❌ HTF not bullish")
        continue

    close = df['Close']
    high = df['High']
    low = df['Low']

    # INDICATORS
    rsi_val = RSIIndicator(close).rsi()
    macd, signal, hist = macd_pine(close)

    psar = PSARIndicator(
        high, low, close,
        step=0.02,
        max_step=0.2
    ).psar()

    last = len(df) - 1

    # ================= BUY CONDITION =================
    if (45 <= rsi_val.iloc[last] <= 65) \
       and (rsi_val.iloc[last-1] < rsi_val.iloc[last]) \
       and (psar.iloc[last] < close.iloc[last]) \
       and (hist.iloc[last] > 0):

        price = close.iloc[last]

        print(f"🔥 BUY SIGNAL: {stock} @ {price}")

        results.append({
            "Stock": stock,
            "Price": round(price, 2),
            "Date": datetime.now().strftime("%Y-%m-%d")
        })

    time.sleep(0.2)


# =========================
# SAVE CSV
# =========================
if results:
    pd.DataFrame(results).to_csv("buy_candidates.csv", index=False)
    print("\n✅ CSV Saved")
else:
    print("\n🎯 No signals today")


# =========================
# GOOGLE SHEET UPDATE 
# =========================
try:
    # Use creds_dict (NO credentials.json)
    gc = gspread.service_account_from_dict(creds_dict)

    sheet_obj = open_sheet_with_retry(gc, "PARABOLIC SAR")
    sheet = sheet_obj.worksheet("DaySAR")

    # Get existing data
    existing_data = sheet.get_all_values()

    # Create set of (Stock, Date)
    existing_set = set()
    for row in existing_data[1:]:  # skip header
        if len(row) >= 3:
            existing_set.add((row[0], row[2]))

    # Filter new rows
    new_rows = []
    for row in results:
        key = (row["Stock"], row["Date"])
        if key not in existing_set:
            new_rows.append([
                row["Stock"],
                row["Price"],
                row["Date"]
            ])

    # Push only new data
    if new_rows:
        sheet.append_rows(new_rows)
        print(f"✅ {len(new_rows)} new rows added")
    else:
        print("ℹ️ No new rows (duplicates skipped)")

except Exception as e:
    print("❌ Sheet Error:", e)
