import asyncio
import json
import structlog
import uuid
import random
from aiomqtt import Client, MqttError
from app.config import settings
from app.utils.tasks import create_background_task

log = structlog.get_logger()

# Reconnection backoff parameters
INITIAL_BACKOFF = 1  # Start with 1 second
MAX_BACKOFF = 60     # Cap at 60 seconds
BACKOFF_MULTIPLIER = 2
MQTT_HANDLER_CONCURRENCY = 4
MQTT_MAX_IN_FLIGHT_MESSAGES = 200

class MQTTService:
    def __init__(self, version: str = "unknown"):
        self.client = None
        self.running = False
        self.paused = False
        self.reconnect_delay = INITIAL_BACKOFF
        self._handler_semaphore = asyncio.Semaphore(MQTT_HANDLER_CONCURRENCY)
        self._in_flight_tasks: set[asyncio.Task] = set()
        self._event_task_tails: dict[str, asyncio.Task] = {}
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

    def _track_handler_task(self, task: asyncio.Task):
        self._in_flight_tasks.add(task)
        task.add_done_callback(lambda done: self._in_flight_tasks.discard(done))

    async def _wait_for_handler_slot(self):
        while len(self._in_flight_tasks) >= MQTT_MAX_IN_FLIGHT_MESSAGES and self.running:
            done, _pending = await asyncio.wait(
                self._in_flight_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                self._in_flight_tasks.discard(task)

    def _extract_frigate_event_id(self, payload: bytes) -> str | None:
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            after = data.get("after")
            if not isinstance(after, dict):
                return None
            event_id = str(after.get("id") or "").strip()
            return event_id or None
        except Exception:
            return None

    async def _dispatch_frigate_message(self, event_processor, payload: bytes):
        async with self._handler_semaphore:
            await event_processor.process_mqtt_message(payload)

    async def _dispatch_audio_message(self, event_processor, payload: bytes):
        async with self._handler_semaphore:
            await event_processor.process_audio_message(payload)

    def _schedule_frigate_message(self, event_processor, payload: bytes) -> asyncio.Task:
        event_id = self._extract_frigate_event_id(payload)
        previous_task = self._event_task_tails.get(event_id or "")

        async def _run():
            if previous_task is not None:
                try:
                    await previous_task
                except asyncio.CancelledError:
                    return
                except Exception:
                    # Prior failures are already logged by task wrapper; continue processing newer state.
                    pass
            if not self.running:
                return
            await self._dispatch_frigate_message(event_processor, payload)

        task_name = f"mqtt_dispatch_frigate:{event_id or 'unknown'}"
        task = create_background_task(_run(), name=task_name)
        self._track_handler_task(task)

        if event_id:
            self._event_task_tails[event_id] = task

            def _cleanup(done: asyncio.Task, eid: str = event_id) -> None:
                if self._event_task_tails.get(eid) is done:
                    self._event_task_tails.pop(eid, None)

            task.add_done_callback(_cleanup)
        return task

    def _schedule_audio_message(self, event_processor, payload: bytes) -> asyncio.Task:
        task = create_background_task(
            self._dispatch_audio_message(event_processor, payload),
            name="mqtt_dispatch_birdnet",
        )
        self._track_handler_task(task)
        return task

    def _cancel_in_flight_tasks(self):
        for task in list(self._in_flight_tasks):
            task.cancel()
        self._in_flight_tasks.clear()
        self._event_task_tails.clear()

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
                            await self._wait_for_handler_slot()
                            self._schedule_frigate_message(event_processor, message.payload)
                        elif topic == birdnet_topic:
                            log.info("Received MQTT message on birdnet topic", payload_len=len(message.payload))
                            await self._wait_for_handler_slot()
                            self._schedule_audio_message(event_processor, message.payload)
                            
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
        self._cancel_in_flight_tasks()
        if self.client:
            # aiomqtt client context manager handles disconnect, but we can break the loop
            pass

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

mqtt_service = MQTTService()
