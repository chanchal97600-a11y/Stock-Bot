import os
import subprocess
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

def send_msg(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )
    except Exception as e:
        print("Send message error:", e)

@app.route("/", methods=["POST"])
def webhook():
    print("WEBHOOK HIT")   # ✅ DEBUG LINE

    data = request.get_json(silent=True)

    if not data or "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if text == "/run":
        send_msg(chat_id, "⏳ Running scanner...")

        try:
            result = subprocess.run(
                ["python3", "sheet_runner.py"],  # ✅ FIXED
                capture_output=True,
                text=True,
                timeout=300
            )

            output = result.stdout if result.stdout else result.stderr
            output = output[-3500:] if output else "Done"

            send_msg(chat_id, "✅ Completed\n\n" + output)

        except subprocess.TimeoutExpired:
            send_msg(chat_id, "❌ Timeout: Script took too long")

        except Exception as e:
            send_msg(chat_id, f"❌ Error: {str(e)}")

    else:
        send_msg(chat_id, "Use /run")

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
