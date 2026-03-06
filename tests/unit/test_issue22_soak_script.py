import importlib.util
import sys
import json
import threading
import time
from pathlib import Path

import pytest


SCRIPT_PATH = Path('/config/workspace/YA-WAMF/scripts/run_issue22_soak.py')
spec = importlib.util.spec_from_file_location('run_issue22_soak', SCRIPT_PATH)
soak = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = soak
assert spec.loader is not None
spec.loader.exec_module(soak)


class _FakePublishInfo:
    def __init__(self, rc=0, publish_after=0.0):
        self.rc = rc
        self._publish_after = publish_after
        self._published_at = time.monotonic() + publish_after

    def is_published(self):
        return time.monotonic() >= self._published_at


class _FakeClient:
    def __init__(self):
        self.on_connect = None
        self.connected = False
        self.loop_started = False
        self.published = []

    def connect(self, host, port, keepalive=30):
        self.connect_args = (host, port, keepalive)
        def _complete_connect():
            time.sleep(0.01)
            self.connected = True
            if self.on_connect is not None:
                self.on_connect(self, None, None, 0)
        threading.Thread(target=_complete_connect, daemon=True).start()

    def loop_start(self):
        self.loop_started = True

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return _FakePublishInfo(rc=0, publish_after=0.01)


def test_build_frigate_payload_can_mark_false_positive():
    payload = json.loads(
        soak._build_frigate_payload(
            event_id='evt-1',
            event_type='update',
            false_positive=True,
        )
    )

    assert payload['type'] == 'update'
    assert payload['after']['false_positive'] is True


def test_connect_mqtt_client_waits_for_connect_callback():
    client = _FakeClient()

    soak._connect_mqtt_client(
        client,
        mqtt_host='mqtt',
        mqtt_port=1883,
        timeout_seconds=0.5,
    )

    assert client.loop_started is True
    assert client.connected is True
    assert client.connect_args == ('mqtt', 1883, 30)


def test_publish_message_waits_until_broker_acknowledges_publish():
    client = _FakeClient()

    soak._publish_message(
        client,
        topic='frigate/events',
        payload='{}',
        timeout_seconds=0.5,
    )

    assert client.published == [('frigate/events', '{}', 1, False)]


class _FakeClientWithoutCallback(_FakeClient):
    def connect(self, host, port, keepalive=30):
        self.connect_args = (host, port, keepalive)
        def _complete_connect():
            time.sleep(0.01)
            self.connected = True
        threading.Thread(target=_complete_connect, daemon=True).start()

    def is_connected(self):
        return self.connected


def test_connect_mqtt_client_accepts_is_connected_without_callback_signal():
    client = _FakeClientWithoutCallback()

    soak._connect_mqtt_client(
        client,
        mqtt_host='mqtt',
        mqtt_port=1883,
        timeout_seconds=0.5,
    )

    assert client.connected is True


def test_build_mosquitto_pub_command_includes_auth_and_payload():
    command = soak._build_mosquitto_pub_command(
        container_name='mosquitto',
        mqtt_host='127.0.0.1',
        mqtt_port=1883,
        mqtt_username='user1',
        mqtt_password='pass1',
        topic='frigate/events',
        payload='{"ok":true}',
    )

    assert command == [
        'docker', 'exec', 'mosquitto', 'mosquitto_pub',
        '-h', '127.0.0.1',
        '-p', '1883',
        '-u', 'user1',
        '-P', 'pass1',
        '-t', 'frigate/events',
        '-m', '{"ok":true}',
    ]
