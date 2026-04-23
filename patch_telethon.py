with open("src/huntx/connectors/telegram_user/connector.py", "r") as f:
    content = f.read()

content = content.replace("client.disconnect()", "client.loop.run_until_complete(client.disconnect()) if getattr(client, 'loop', None) and not client.loop.is_closed() else None")

with open("src/huntx/connectors/telegram_user/connector.py", "w") as f:
    f.write(content)
