import asyncio
import structlog
import uuid
from aiomqtt import Client, MqttError
from app.config import settings

log = structlog.get_logger()

class MQTTService:
    def __init__(self, version: str = "unknown"):
        self.client = None
        self.running = False
        # Simplified Client ID: yawamf-{git_hash}
        # version format is usually "2.0.0+abc1234"
        git_hash = version.split('+')[-1] if '+' in version else "unknown"
        self.client_id = f"yawamf-{git_hash}"

    async def start(self, event_processor):
        self.running = True

        # Validate MQTT settings
        if not settings.frigate.mqtt_server:
            log.error("MQTT server not configured. Set FRIGATE__MQTT_SERVER environment variable.")
            return
            
        log.info("Starting MQTT Service", client_id=self.client_id)

        while self.running:
            try:
                # Only pass credentials if auth is enabled and credentials are provided
                client_kwargs = {
                    "hostname": settings.frigate.mqtt_server,
                    "port": settings.frigate.mqtt_port,
                    "identifier": self.client_id
                }
                if settings.frigate.mqtt_auth and settings.frigate.mqtt_username:
                    client_kwargs["username"] = settings.frigate.mqtt_username
                    client_kwargs["password"] = settings.frigate.mqtt_password

                async with Client(**client_kwargs) as client:
                    self.client = client
                    
                    # Frigate Topic
                    frigate_topic = f"{settings.frigate.main_topic}/events"
                    await client.subscribe(frigate_topic)
                    
                    # BirdNET Topic (BirdNET-Go default)
                    birdnet_topic = settings.frigate.audio_topic
                    await client.subscribe(birdnet_topic)
                    
                    log.info("Connected to MQTT", topics=[frigate_topic, birdnet_topic])

                    async for message in client.messages:
                        topic = message.topic.value
                        if topic == frigate_topic:
                            log.info("Received MQTT message on frigate topic", payload_len=len(message.payload))
                            await event_processor.process_mqtt_message(message.payload)
                        elif topic == birdnet_topic:
                            log.info("Received MQTT message on birdnet topic", payload_len=len(message.payload))
                            await event_processor.process_audio_message(message.payload)
                            
            except MqttError as e:
                log.error("MQTT connection lost", error=str(e))
                await asyncio.sleep(5)  # Reconnect delay
            except Exception as e:
                log.error("Unexpected error in MQTT service", error=str(e))
                await asyncio.sleep(5)

    async def publish(self, topic: str, payload: dict | str) -> bool:
        """Publish a message to a specific topic."""
        if not self.client:
            log.warning("Cannot publish - MQTT client not connected")
            return False
            
        try:
            import json
            if isinstance(payload, dict):
                payload = json.dumps(payload)
                
            await self.client.publish(topic, payload)
            log.info("Published MQTT message", topic=topic)
            return True
        except Exception as e:
            log.error("Failed to publish message", topic=topic, error=str(e))
            return False

    async def stop(self):
        self.running = False
        if self.client:
            # aiomqtt client context manager handles disconnect, but we can break the loop
            pass

mqtt_service = MQTTService()
