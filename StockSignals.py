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
sheet = gc.open("PARABOLIC SAR").worksheet("StockSignals")

# =========================
# MACD (FIXED)
# =========================
def macd_hist(series):
    ema_fast = series.ewm(span=12, adjust=False).mean()
    ema_slow = series.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line - signal

# =========================
# CLEAN SERIES
# =========================
def clean(x):
    if isinstance(x, pd.DataFrame):
        x = x.iloc[:, 0]
    return pd.Series(x.values, index=x.index)

# =========================
# HTF TREND (FIXED ALIGNMENT)
# =========================
def get_htf_trend_at_date(htf_df, date):

    # ✅ FIX: no future data
    df = htf_df[htf_df.index <= date]

    if len(df) < 30:
        return False

    close = clean(df["Close"])

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()

    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    return hist.iloc[-1] > 0

# =========================
# NIFTY TREND
# =========================
def nifty_trend_at_date(date, nifty_df):
    df = nifty_df[nifty_df.index <= date].copy()

    if len(df) < 100:
        return "BEARISH"

    close = clean(df["Close"])
    sma_100 = close.rolling(100).mean()

    return "BULLISH" if close.iloc[-1] > sma_100.iloc[-1] else "BEARISH"

# =========================
# DATA
# =========================
def get_data(symbol):
    df = yf.download(symbol + ".NS", period="2y", interval="1d", progress=False)
    if df.empty:
        return None
    return df

# =========================
# CORE LOGIC
# =========================
def get_last_trade(df, htf_df, symbol, nifty_df):

    close = clean(df["Close"])
    high = clean(df["High"])
    low = clean(df["Low"])
    open_ = clean(df["Open"])

    rsi = RSIIndicator(close).rsi()
    hist = macd_hist(close)
    psar = PSARIndicator(high=high, low=low, close=close).psar()

    data = pd.DataFrame({
        "Close": close,
        "High": high,
        "Low": low,
        "Open": open_,
        "rsi": rsi,
        "hist": hist,
        "psar": psar
    }).dropna()

    last_trade = None

    for i in range(50, len(data) - 1):

        date = data.index[i]

        # ✅ HTF FILTER
        if not get_htf_trend_at_date(htf_df, date):
            continue

        # ✅ ENTRY CONDITIONS
        if (
            45 <= data["rsi"].iloc[i] <= 65 and
            data["rsi"].iloc[i] > data["rsi"].iloc[i - 1] and
            data["hist"].iloc[i] > 0 and
            data["psar"].iloc[i] < data["Close"].iloc[i]
        ):

            entry_price = data["Open"].iloc[i + 1]
            entry_date = data.index[i + 1]

            market_trend = nifty_trend_at_date(entry_date, nifty_df)

            tp = entry_price * 1.25
            sl = entry_price * 0.85

            result = "OPEN"
            exit_price = None
            exit_date = None

            max_days = 100
            end = min(i + 1 + max_days, len(data))

            for j in range(i + 1, end):

                if data["High"].iloc[j] >= tp:
                    result = "CLOSED"
                    exit_price = tp
                    exit_date = data.index[j]
                    break

                elif data["Low"].iloc[j] <= sl:
                    result = "CLOSED"
                    exit_price = sl
                    exit_date = data.index[j]
                    break

            if result == "OPEN" and (end - (i + 1)) >= max_days:
                result = "CLOSED"
                exit_price = data["Close"].iloc[end - 1]
                exit_date = data.index[end - 1]

            last_trade = [
                entry_date,
                entry_price,
                result,
                exit_date,
                exit_price,
                market_trend
            ]

    return last_trade

# =========================
# MAIN
# =========================
file = "stocks.txt"
stocks = [s.strip().upper() for s in open(file) if s.strip()]

nifty_df = yf.download("^NSEI", period="10y", interval="1d", progress=False)

results = []

for stock in stocks:
    print("Processing:", stock)

    df = get_data(stock)

    if df is None or len(df) < 200:
        print(f"SKIPPED (DATA ISSUE): {stock}")
        continue

    htf_df = yf.download(stock + ".NS", interval="1wk", period="5y", progress=False)

    if htf_df is None or htf_df.empty:
        print(f"SKIPPED (HTF ISSUE): {stock}")
        continue

    trade = get_last_trade(df, htf_df, stock, nifty_df)

    if trade:
        results.append([
            stock,
            str(trade[0].date()),
            round(trade[1], 2),
            trade[2],
            str(trade[3].date()) if trade[3] else "",
            round(trade[4], 2) if trade[4] else "",
            trade[5]
        ])
    else:
        print(f"NO TRADE: {stock}")

# =========================
# GOOGLE SHEET FULL UPDATE (FIXED)
# =========================
headers = ["Stock","Buy Date","Buy Price","Status","Sell Date","Sell Price","Market Trend"]

print("Updating sheet...")

all_data = [headers] + results

sheet.clear()
sheet.update("A1", all_data)

print(f"✅ DONE: {len(results)} stocks updated")
