import asyncio
import json
from aiomqtt import Client

async def main():
    print("Connecting to mosquitto.general_brg...")
    try:
        async with Client("mosquitto.general_brg", 1883, username="jellman86", password="mqqtfuckyou123") as client:
            print("Connected!")
            await client.subscribe("frigate/events")
            print("Subscribed to frigate/events. Waiting 30s for events...")
            async for message in client.messages:
                print(f"Topic: {message.topic}")
                data = json.loads(message.payload)
                print(json.dumps(data, indent=2))
                break # Just catch one
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())