import asyncio

async def main():
    try:
        raise ValueError("test")
    except Exception as e:
        print("caught", e)

asyncio.run(main())
