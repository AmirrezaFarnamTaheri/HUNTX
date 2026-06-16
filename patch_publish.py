import os
import re

with open("src/huntx/pipeline/publish.py", "r") as f:
    text = f.read()

repl = """        publish_bot_token = os.getenv("PUBLISH_BOT_TOKEN")
        ingest_token = os.getenv("TELEGRAM_TOKEN")
        default_token = publish_bot_token or ingest_token
        if (not publish_bot_token) and default_token and ingest_token and default_token == ingest_token:
            logger.warning(
                "⚠️  WARNING (F-09): The publish pipeline is using TELEGRAM_TOKEN because PUBLISH_BOT_TOKEN is unset. "
                "If the persistent bot is also running, this will cause 409 Conflict errors. "
                "Please configure a distinct PUBLISH_BOT_TOKEN."
            )"""

text = text.replace("""        default_token = os.getenv("PUBLISH_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        ingest_token = os.getenv("TELEGRAM_TOKEN")
        if default_token and ingest_token and default_token == ingest_token:
            logger.warning(
                "⚠️  WARNING (F-09): The publish pipeline is using TELEGRAM_TOKEN because PUBLISH_BOT_TOKEN is unset. "
                "If the persistent bot is also running, this will cause 409 Conflict errors. "
                "Please configure a distinct PUBLISH_BOT_TOKEN."
            )""", repl)

with open("src/huntx/pipeline/publish.py", "w") as f:
    f.write(text)
