import subprocess
import pandas as pd
import gspread
import os
from datetime import datetime
import requests

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
        print("📨 Telegram:", r.status_code, r.text)
    except Exception as e:
        print("❌ Telegram error:", e)

# =========================
# RUN SCANNER
# =========================
print("🚀 Running scanner...")
subprocess.run(["python", "nse_scanning.py"])

# =========================
# CHECK CSV
# =========================
if not os.path.exists("buy_candidates.csv"):
    print("❌ buy_candidates.csv not found")
    exit()

df = pd.read_csv("buy_candidates.csv")

print("\n📊 RAW DATA:")
print(df)

if df.empty:
    print("❌ No stocks from scanner")
    exit()

# =========================
# CLEAN DATA
# =========================
required_cols = ["Price", "Total Trades", "Wins", "Losses", "Timeout", "Win%"]

for col in required_cols:
    if col not in df.columns:
        df[col] = 0

for col in required_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# =========================
# FILTER LOGIC
# =========================
df = df[(df["Win%"] >= 50) & (df["Total Trades"] >= 3)]

print(f"\n🎯 After filter: {len(df)} stocks")

if df.empty:
    print("⚠️ No strong stocks → uploading ALL for debug")
    df = pd.read_csv("buy_candidates.csv")

# =========================
# GOOGLE SHEETS AUTH
# =========================
print("\n🔐 Loading credentials from Railway ENV...")

try:
    creds_dict = {
        "type": os.environ.get("type"),
        "project_id": os.environ.get("project_id"),
        "private_key_id": os.environ.get("private_key_id"),
        "private_key": os.environ.get("private_key").replace("\\n", "\n"),
        "client_email": os.environ.get("client_email"),
        "client_id": os.environ.get("client_id"),
        "auth_uri": os.environ.get("auth_uri"),
        "token_uri": os.environ.get("token_uri"),
        "auth_provider_x509_cert_url": os.environ.get("auth_provider_x509_cert_url"),
        "client_x509_cert_url": os.environ.get("client_x509_cert_url")
    }

    gc = gspread.service_account_from_dict(creds_dict)
    print("✅ Credentials loaded successfully")

except Exception as e:
    print("❌ Credential error:", e)
    exit()

# =========================
# OPEN SHEET
# =========================
SHEET_FILE = "PARABOLIC SAR"
WORKSHEET_NAME = "DaySAR"

try:
    sh = gc.open(SHEET_FILE)
    sheet = sh.worksheet(WORKSHEET_NAME)
    print(f"✅ Connected to {SHEET_FILE} → {WORKSHEET_NAME}")
except Exception as e:
    print("❌ Sheet open error:", e)
    exit()

# =========================
# AVOID DUPLICATES (CHECK EXISTING)
# =========================
existing_records = sheet.get_all_records()

today = datetime.now().strftime("%Y-%m-%d")
existing_today = set()

for rec in existing_records:
    if str(rec.get("Date", "")) == today:
        existing_today.add(str(rec.get("Stock", "")).strip().upper())

print("📌 Already uploaded today:", existing_today)

# =========================
# PREPARE NEW ROWS
# =========================
now = datetime.now()
new_rows = []

for _, row in df.iterrows():
    stock = str(row["Stock"]).strip().upper()

    if stock in existing_today:
        print(f"⏭️ Skipping duplicate: {stock}")
        continue

    new_rows.append([
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        stock,
        row["Price"],
        int(row["Total Trades"]),
        int(row["Wins"]),
        int(row["Losses"]),
        int(row["Timeout"]),
        round(row["Win%"], 2),
        "Python System"
    ])

# =========================
# UPLOAD TO SHEETS + TELEGRAM
# =========================
if new_rows:
    sheet.append_rows(new_rows)
    print(f"\n🚀 Uploaded {len(new_rows)} rows")

    for r in new_rows:
        msg = f"📌 {r[2]} | ₹{r[3]}"
        send_telegram_message(msg)

else:
    print("❌ No new stocks to upload")

print("✅ DONE")
