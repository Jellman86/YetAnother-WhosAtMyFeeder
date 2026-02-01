import asyncio
import structlog
import uuid
import random
from aiomqtt import Client, MqttError
from app.config import settings

log = structlog.get_logger()

# Reconnection backoff parameters
INITIAL_BACKOFF = 1  # Start with 1 second
MAX_BACKOFF = 60     # Cap at 60 seconds
BACKOFF_MULTIPLIER = 2

class MQTTService:
    def __init__(self, version: str = "unknown"):
        self.client = None
        self.running = False
        self.paused = False
        self.reconnect_delay = INITIAL_BACKOFF
        # Simplified Client ID: yawamf-{git_hash}
        # version format is usually "2.0.0+abc1234"
        git_hash = version.split('+')[-1] if '+' in version else "unknown"

        # If hash is unknown (local dev or missing build arg), append session ID to avoid collisions
        if git_hash == "unknown":
            session_id = str(uuid.uuid4())[:8]
            self.client_id = f"yawamf-unknown-{session_id}"
        else:
            self.client_id = f"yawamf-{git_hash}"

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff with jitter.

        Returns delay in seconds with random jitter to prevent thundering herd.
        """
        # Add ±25% jitter to prevent connection storms
        jitter = random.uniform(0.75, 1.25)
        delay = min(self.reconnect_delay * jitter, MAX_BACKOFF)
        return delay

    def _increase_backoff(self):
        """Increase backoff delay exponentially."""
        self.reconnect_delay = min(self.reconnect_delay * BACKOFF_MULTIPLIER, MAX_BACKOFF)

    def _reset_backoff(self):
        """Reset backoff delay after successful connection."""
        self.reconnect_delay = INITIAL_BACKOFF

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

                    # Reset backoff on successful connection
                    self._reset_backoff()

                    async for message in client.messages:
                        if self.paused:
                            continue
                        # Check for topic changes in settings
                        if settings.frigate.audio_topic != birdnet_topic:
                            log.info("MQTT Audio topic changed in settings, reconnecting...", 
                                     old=birdnet_topic, new=settings.frigate.audio_topic)
                            break # This breaks the 'async for', causing a reconnection with new settings

                        topic = message.topic.value
                        if topic == frigate_topic:
                            log.info("Received MQTT message on frigate topic", payload_len=len(message.payload))
                            await event_processor.process_mqtt_message(message.payload)
                        elif topic == birdnet_topic:
                            log.info("Received MQTT message on birdnet topic", payload_len=len(message.payload))
                            await event_processor.process_audio_message(message.payload)
                            
            except MqttError as e:
                delay = self._calculate_backoff()
                log.error("MQTT connection lost, retrying...",
                         error=str(e),
                         retry_delay=f"{delay:.1f}s",
                         backoff_level=self.reconnect_delay)
                await asyncio.sleep(delay)
                self._increase_backoff()
            except Exception as e:
                delay = self._calculate_backoff()
                log.error("Unexpected error in MQTT service, retrying...",
                         error=str(e),
                         retry_delay=f"{delay:.1f}s",
                         backoff_level=self.reconnect_delay)
                await asyncio.sleep(delay)
                self._increase_backoff()

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

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

mqtt_service = MQTTService()
