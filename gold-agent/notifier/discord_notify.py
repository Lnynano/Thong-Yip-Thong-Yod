"""
notifier/discord_notify.py
Send trading signals to Discord via webhook.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

_COLORS = {
    "BUY":  0x00ff88,
    "SELL": 0xff4444,
    "HOLD": 0xaaaaaa,
}

_EMOJI = {
    "BUY":  "🟢",
    "SELL": "🔴",
    "HOLD": "⏸",
}


def send_signal(
    decision: str,
    confidence: int,
    price_thb: float,
    reasoning: str = "",
    will_trade: bool = False,
) -> bool:
    """
    Post a trading signal embed to Discord.

    Returns True on success, False on failure.
    """
    if not _WEBHOOK_URL:
        print("[discord] DISCORD_WEBHOOK_URL not set — skipping")
        return False

    emoji    = _EMOJI.get(decision, "⏸")
    color    = _COLORS.get(decision, 0xaaaaaa)
    tag = ""
    if will_trade:
        if decision == "BUY":
            if confidence >= 85:
                tag = "**PLACE ORDER NOW (ใช้เงิน 100% ของพอร์ต)**"
            elif confidence >= 75:
                tag = "**PLACE ORDER NOW (ใช้เงิน 95% ของพอร์ต)**"
            else:
                tag = "**PLACE ORDER NOW (ใช้เงิน 90% ของพอร์ต)**"
        elif decision == "SELL":
            tag = "**PLACE ORDER NOW (ขายออกทั้งหมด)**"
    else:
        if decision in ("BUY", "SELL"):
            tag = "*[⚠️ NO ACTION]* ความมั่นใจไม่ถึงเกณฑ์ 65% (แนะนำให้รอดูสถานการณ์)"
            
    short_reason = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning

    mention  = "@everyone " if will_trade else ""
    payload = {
        "content": mention,
        "embeds": [{
            "title"      : f"{emoji} {decision}  |  Confidence: {confidence}%",
            "description": f"**Price:** ฿{price_thb:,.0f}\n{tag}\n\n{short_reason}",
            "color"      : color,
            "footer"     : {"text": "Thong Yip Thong Yod · Gold Agent"},
        }]
    }

    try:
        resp = requests.post(_WEBHOOK_URL, json=payload, timeout=5)
        resp.raise_for_status()
        print(f"[discord] Sent {decision} signal")
        return True
    except Exception as e:
        print(f"[discord] Failed: {e}")
        return False


