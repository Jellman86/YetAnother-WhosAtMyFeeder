import asyncio
import json
import os
from aiomqtt import Client

async def main():
    print("Connecting to mosquitto.general_brg...")
    try:
        host = os.environ.get("YA_WAMF_MQTT_HOST", "mosquitto.general_brg")
        port = int(os.environ.get("YA_WAMF_MQTT_PORT", "1883"))
        username = os.environ.get("YA_WAMF_MQTT_USERNAME")
        password = os.environ.get("YA_WAMF_MQTT_PASSWORD")

        # NOTE: This is a local debugging script. Never hardcode credentials in repo.
        async with Client(host, port, username=username, password=password) as client:
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
