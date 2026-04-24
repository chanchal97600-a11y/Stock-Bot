import os
import subprocess
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ["TELEGRAM_TOKEN"]

def send_msg(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

@app.route("/", methods=["POST"])
def webhook():
    data = request.json

    if "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if text == "/run":
        send_msg(chat_id, "⏳ Running scanner...")

        try:
            result = subprocess.run(
                ["python", "sheet_runner.py"],
                capture_output=True,
                text=True
            )

            output = result.stdout[-3500:] if result.stdout else "Done"
            send_msg(chat_id, "✅ Completed\n\n" + output)

        except Exception as e:
            send_msg(chat_id, f"❌ Error: {str(e)}")

    else:
        send_msg(chat_id, "Use /run")

    return "ok"

app.run(host="0.0.0.0", port=5000)