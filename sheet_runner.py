import subprocess
import pandas as pd
import gspread
import os
from datetime import datetime
import pytz
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
india = pytz.timezone("Asia/Kolkata")

# =========================
# LOAD DATA FROM GOOGLE SHEET
# =========================
records = sheet.get_all_records()

if not records:
    print("❌ No data in sheet")
    exit()

df = pd.DataFrame(records)

# Ensure proper types
df["Stock"] = df["Stock"].astype(str)
df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)

print(f"📊 Loaded {len(df)} rows from Google Sheet")

if df.empty:
    print("❌ No BUY candidates")
    exit()

# =========================
# FETCH EXISTING RECORDS
# =========================
existing_records = sheet.get_all_records()

today_str = datetime.now(india).strftime("%Y-%m-%d")

# =========================
# BUY ALERTS ONLY
# =========================
print("📈 Sending BUY alerts...")

sent_today = set()

for _, row in df.iterrows():

    stock = str(row["Stock"]).upper().strip()
    price = float(row["Price"])
    date = str(row["Date"]).split(" ")[0]

    # Skip invalid stock names
    if stock == "" or stock == "0":
        continue

    # Send only today's signals
    if date == today_str:

        key = (stock, date)

        if key not in sent_today:

            send_telegram_message(
                f"🟢 BUY SIGNAL\n"
                f"📌 Stock: {stock}\n"
                f"💰 Price: ₹{price}"
            )

            sent_today.add(key)

            print(f"📨 Sent BUY alert: {stock}")

# =========================
# SELL LOGIC
# =========================
print("🔍 Checking SELL conditions...")

today = datetime.now(india)

# start=2 because Google Sheet row 1 is header
for idx, rec in enumerate(existing_records, start=2):

    try:

        # =========================
        # STATUS CHECK
        # =========================
        status = str(rec.get("Status", "OPEN")).upper()

        # Skip already sold trades
        if status == "SOLD":
            continue

        # =========================
        # BASIC DATA
        # =========================
        stock = str(rec.get("Stock", "")).upper().strip()

        buy_price = float(rec.get("Price", 0))

        buy_date_str = rec.get("Date")

        if not stock or not buy_date_str or buy_price == 0:
            continue

        # =========================
        # BUY DATE
        # =========================
        buy_date = datetime.strptime(
            buy_date_str,
            "%Y-%m-%d"
        )

        # Fix .NS duplication
        ticker = stock if stock.endswith(".NS") else stock + ".NS"

        data = yf.Ticker(ticker).history(period="1d")

        if data.empty:
            continue

        current_price = float(data["Close"].iloc[-1])

        target = buy_price * 1.25
        stoploss = buy_price * 0.85

        days = (today - buy_date).days

        # TARGET HIT
        if current_price >= target:

            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n"
                f"🎯 TARGET HIT"
            )

            sheet.update_cell(idx, 5, "SOLD")

        # STOP LOSS
        elif current_price <= stoploss:

            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n"
                f"🛑 STOP LOSS"
            )

            sheet.update_cell(idx, 5, "SOLD")

        # TIME EXIT
        elif days >= 100:

            send_telegram_message(
                f"🔻 SELL {stock} @ ₹{current_price:.2f}\n"
                f"⏳ TIME EXIT (100 Days)"
            )

            sheet.update_cell(idx, 5, "SOLD")

    except Exception as e:
        print("❌ SELL Error:", e)

print("✅ DONE")

# =========================
# RUN StockSignals
# =========================
try:
    import StockSignals

    StockSignals.run()

except Exception as e:
    print("❌ Error running StockSignals:", e)
