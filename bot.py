import os
import subprocess
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")


def send_msg(chat_id, text):
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )
        print("SEND STATUS:", res.status_code)
        print("SEND RESPONSE:", res.text)
    except Exception as e:
        print("Send message error:", e)


@app.route("/", methods=["POST"])
def webhook():
    print("WEBHOOK HIT")

    data = request.get_json(silent=True)
    print("FULL DATA:", data)

    if not data or "message" not in data:
        return "ok"

    chat = data["message"].get("chat", {})
    chat_id = chat.get("id")

    text = data["message"].get("text", "")
    print("TEXT RECEIVED:", text)

    if not chat_id:
        return "ok"

    # =========================
    # COMMAND HANDLER
    # =========================
    if text and text.strip().startswith("/run"):
        send_msg(chat_id, "⏳ Running scanner...")

        try:
            result = subprocess.run(
                ["python3", "sheet_runner.py"],
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

    elif text:
        send_msg(chat_id, f"Use /run (you sent: {text})")

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
