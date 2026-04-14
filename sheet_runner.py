import subprocess
import pandas as pd
import gspread
import os
from datetime import datetime
import requests
import yfinance as yf

# =========================
# TELEGRAM CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL")

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
        print("⚠️ Telegram variables missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(url, data=payload)
        print("📨 Telegram:", r.status_code)
    except Exception as e:
        print("❌ Telegram error:", e)

# =========================
# RUN SCANNER
# =========================
print("🚀 Running scanner...")
subprocess.run(["python", "nse_scanning.py"])

# =========================
# LOAD BUY CANDIDATES
# =========================
if not os.path.exists("buy_candidates.csv"):
    print("❌ buy_candidates.csv not found")
    exit()

df = pd.read_csv("buy_candidates.csv")

if df.empty:
    print("❌ No BUY candidates")
    exit()

# =========================
# CLEAN & FILTER
# =========================
required_cols = ["Stock", "Price", "Total Trades", "Wins", "Losses", "Timeout", "Win%"]

for col in required_cols:
    if col not in df.columns:
        df[col] = 0

df[required_cols] = df[required_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

df = df[(df["Win%"] >= 50) & (df["Total Trades"] >= 3)]

if df.empty:
    print("⚠️ No strong BUY → using all")
    df = pd.read_csv("buy_candidates.csv")

# =========================
# GOOGLE SHEETS AUTH
# =========================
creds_dict = {
    "type": os.environ.get("type"),
    "project_id": os.environ.get("project_id"),
    "private_key_id": os.environ.get("private_key_id"),
    "private_key": os.environ.get("private_key", "").replace("\\n", "\n"),
    "client_email": os.environ.get("client_email"),
    "client_id": os.environ.get("client_id"),
    "auth_uri": os.environ.get("auth_uri"),
    "token_uri": os.environ.get("token_uri"),
    "auth_provider_x509_cert_url": os.environ.get("auth_provider_x509_cert_url"),
    "client_x509_cert_url": os.environ.get("client_x509_cert_url")
}

gc = gspread.service_account_from_dict(creds_dict)
sheet = gc.open("PARABOLIC SAR").worksheet("DaySAR")

# =========================
# FETCH EXISTING RECORDS
# =========================
existing_records = sheet.get_all_records()

today_str = datetime.now().strftime("%Y-%m-%d")

existing_today = {
    str(r["Stock"]).upper()
    for r in existing_records
    if str(r.get("Date", "")) == today_str
}

# =========================
# BUY ALERTS + SHEET UPDATE
# =========================
print("📈 Checking BUY signals...")

for _, row in df.iterrows():
    stock = str(row["Stock"]).upper()
    price = float(row["Price"])

    if stock not in existing_today:
        send_telegram_message(f"🟢 BUY {stock} @ ₹{price}")

        # ✅ Save to Google Sheet (prevents duplicate alerts)
        try:
            sheet.append_row([
                stock,
                price,
                today_str
            ])
            print(f"✅ Saved {stock} to sheet")
        except Exception as e:
            print("❌ Sheet update error:", e)

# =========================
# SELL LOGIC
# =========================
print("🔍 Checking SELL conditions...")

today = datetime.now()

for rec in existing_records:
    try:
        stock = rec.get("Stock")
        buy_price = float(rec.get("Price", 0))
        buy_date_str = rec.get("Date")

        if not stock or not buy_date_str:
            continue

        buy_date = datetime.strptime(buy_date_str, "%Y-%m-%d")

        data = yf.Ticker(stock + ".NS").history(period="1d")
        if data.empty:
            continue

        current_price = float(data["Close"].iloc[-1])

        target = buy_price * 1.25
        stoploss = buy_price * 0.85
        days = (today - buy_date).days

        if current_price >= target:
            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n🎯 TARGET HIT"
            )

        elif current_price <= stoploss:
            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n🛑 STOP LOSS"
            )

        elif days >= 200:
            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n⏳ TIME EXIT (200 Days)"
            )

    except Exception as e:
        print("❌ SELL Error:", e)

print("✅ DONE")
