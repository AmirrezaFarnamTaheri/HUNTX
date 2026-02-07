from telethon.sync import TelegramClient
from telethon.sessions import StringSession

print("This script will generate a Telethon session string.")
print("You need your API_ID and API_HASH from https://my.telegram.org")

api_id_input = input("Enter API_ID: ").strip()
if not api_id_input:
    print("API_ID required")
    exit(1)

try:
    api_id = int(api_id_input)
except ValueError:
    print("API_ID must be an integer")
    exit(1)

api_hash = input("Enter API_HASH: ").strip()
if not api_hash:
    print("API_HASH required")
    exit(1)

print("\nConnecting... (Follow instructions to login)")

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n------------------------------------------------")
    print("SESSION_STRING:")
    print(client.session.save())
    print("------------------------------------------------")
    print("\nCopy the SESSION_STRING above (excluding lines) and save it as TELEGRAM_USER_SESSION in GitHub Secrets.")
