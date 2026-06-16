import re

with open("tests/test_telegram_user_connector.py", "r") as f:
    text = f.read()

text = text.replace("@unittest.skip('Failing due to AsyncMock conversion')", "")
text = text.replace("mock_client.connect = AsyncMock()", "mock_client.connect = AsyncMock()\n        mock_client.disconnect = AsyncMock()\n        mock_client.download_media = AsyncMock()")

# To handle iteration of items synchronously wrapping async methods, the tests wrap `list_new` which returns an iterator.
# It currently loops over async_iter using loop.run_until_complete inside `__iter__`. This requires `download_media`, `connect`, etc. to be AsyncMock.

with open("tests/test_telegram_user_connector.py", "w") as f:
    f.write(text)
