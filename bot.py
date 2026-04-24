import os
import subprocess
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 👉 CHANGE THIS if you want channel output
CHANNEL_ID = "@YourChannelName"   # OR "-100xxxxxxxxxx"


def send_msg(chat_id, text):
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )
        print("SEND STATUS:", res.status_code)
        print("SEND RESPONSE:", res.text)
    except Exception as e:
        print("Send error:", e)


@app.route("/", methods=["POST"])
def webhook():
    print("WEBHOOK HIT")

    data = request.get_json(silent=True)
    print("DATA:", data)

    if not data or "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    print("TEXT:", text)

    # ======================
    # RUN COMMAND
    # ======================
    if text and text.strip().startswith("/run"):

        send_msg(chat_id, "⏳ Running scanner...")

        try:
            result = subprocess.run(
                ["python3", "-u", "sheet_runner.py"],  # 🔥 IMPORTANT FIX
                capture_output=True,
                text=True,
                timeout=300
            )

            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            print("CODE:", result.returncode)

            output = result.stdout or result.stderr
            output = output.strip()

            if not output:
                output = "❌ No output from scanner"

            output = output[-3500:]

            send_msg(chat_id, "✅ Completed\n\n" + output)

        except subprocess.TimeoutExpired:
            send_msg(chat_id, "❌ Timeout: script took too long")

        except Exception as e:
            send_msg(chat_id, f"❌ Error: {str(e)}")

    else:
        send_msg(chat_id, f"Use /run (you sent: {text})")

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
