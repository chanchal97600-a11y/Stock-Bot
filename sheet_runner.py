import subprocess
import pandas as pd
import gspread
import os
import json
from datetime import datetime

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
raw = os.environ.get("GOOGLE_CREDENTIALS")

print("\n🔍 ENV CHECK")
print("Exists:", raw is not None)

if not raw:
    print("❌ GOOGLE_CREDENTIALS missing")
    exit()

try:
    creds_dict = json.loads(raw)
except Exception as e:
    print("❌ Failed to load JSON:", e)
    exit()

gc = gspread.service_account_from_dict(creds_dict)

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
# READ EXISTING DATA
# =========================
all_data = sheet.get_all_values()

header = [
    "Date", "Time", "Stock", "Price",
    "Total Trades", "Wins", "Losses",
    "Timeout", "Win%", "Source"
]

if all_data:
    rows = all_data[1:]
    rows = [r[:10] + [""]*(10-len(r)) for r in rows]
    history = pd.DataFrame(rows, columns=header)
else:
    history = pd.DataFrame(columns=header)

# =========================
# PREPARE NEW ROWS
# =========================
now = datetime.now()
new_rows = []

for _, row in df.iterrows():
    new_rows.append([
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        str(row["Stock"]).strip(),
        row["Price"],
        int(row["Total Trades"]),
        int(row["Wins"]),
        int(row["Losses"]),
        int(row["Timeout"]),
        round(row["Win%"], 2),
        "Python System"
    ])

print("\n📤 Rows to upload:")
for r in new_rows:
    print(r)

# =========================
# UPLOAD
# =========================
if new_rows:
    sheet.append_rows(new_rows)
    print(f"\n🚀 Uploaded {len(new_rows)} rows")
else:
    print("❌ Nothing to upload")

print("✅ DONE")
