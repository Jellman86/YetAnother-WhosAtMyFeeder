import pytest

from app.services.classifier_worker_protocol import (
    build_classify_request,
    build_classify_video_request,
    build_error_event,
    build_heartbeat_event,
    build_progress_event,
    build_ready_event,
    build_runtime_recovery_event,
    build_result_event,
    decode_protocol_message,
    encode_protocol_message,
)


def test_classifier_worker_protocol_round_trips_ready_message():
    encoded = encode_protocol_message(build_ready_event(worker_generation=2))

    decoded = decode_protocol_message(encoded)

    assert decoded["type"] == "ready"
    assert decoded["worker_generation"] == 2


def test_classifier_worker_protocol_round_trips_heartbeat_message():
    encoded = encode_protocol_message(
        build_heartbeat_event(worker_generation=3, request_id="req-1", busy=True)
    )

    decoded = decode_protocol_message(encoded)

    assert decoded["type"] == "heartbeat"
    assert decoded["worker_generation"] == 3
    assert decoded["request_id"] == "req-1"
    assert decoded["busy"] is True


def test_classifier_worker_protocol_round_trips_result_message():
    encoded = encode_protocol_message(
        build_result_event(
            worker_generation=4,
            request_id="req-2",
            work_id="live-9",
            lease_token=7,
            results=[{"label": "Robin", "score": 0.91}],
        )
    )

    decoded = decode_protocol_message(encoded)

    assert decoded["type"] == "result"
    assert decoded["work_id"] == "live-9"
    assert decoded["lease_token"] == 7
    assert decoded["results"][0]["label"] == "Robin"


def test_classifier_worker_protocol_round_trips_error_message():
    encoded = encode_protocol_message(
        build_error_event(
            worker_generation=5,
            request_id="req-3",
            work_id="background-2",
            lease_token=1,
            error="boom",
        )
    )

    decoded = decode_protocol_message(encoded)

    assert decoded["type"] == "error"
    assert decoded["error"] == "boom"


def test_classifier_worker_protocol_round_trips_runtime_recovery_message():
    encoded = encode_protocol_message(
        build_runtime_recovery_event(
            worker_generation=6,
            request_id="req-5",
            work_id="live-11",
            lease_token=3,
            recovery={
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "GPU",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_cpu",
                "detail": "invalid probabilities",
                "at": 123.0,
            },
        )
    )

    decoded = decode_protocol_message(encoded)

    assert decoded["type"] == "runtime_recovery"
    assert decoded["recovery"]["failed_provider"] == "GPU"
    assert decoded["recovery"]["recovered_provider"] == "intel_cpu"


def test_classifier_worker_protocol_rejects_malformed_message():
    with pytest.raises(ValueError, match="protocol message"):
        decode_protocol_message(b'{"hello":"world"}\n')


def test_classifier_worker_protocol_builds_classify_request():
    message = build_classify_request(
        worker_generation=6,
        request_id="req-4",
        work_id="live-10",
        lease_token=2,
        image_b64="abc123",
        camera_name="front",
        model_id="default",
    )

    assert message["type"] == "classify"
    assert message["request_id"] == "req-4"
    assert message["image_b64"] == "abc123"
    assert message["camera_name"] == "front"
    assert message["model_id"] == "default"


def test_classifier_worker_protocol_round_trips_video_messages():
    request = build_classify_video_request(
        worker_generation=7,
        request_id="req-video",
        work_id="video-1",
        lease_token=9,
        video_path="/tmp/demo.mp4",
        stride=5,
        max_frames=12,
    )
    progress = build_progress_event(
        worker_generation=7,
        request_id="req-video",
        work_id="video-1",
        lease_token=9,
        current_frame=3,
        total_frames=12,
        frame_score=0.81,
        top_label="Robin",
    )

    decoded_request = decode_protocol_message(encode_protocol_message(request))
    decoded_progress = decode_protocol_message(encode_protocol_message(progress))

    assert decoded_request["type"] == "classify_video"
    assert decoded_request["video_path"] == "/tmp/demo.mp4"
    assert decoded_progress["type"] == "progress"
    assert decoded_progress["current_frame"] == 3
    assert decoded_progress["top_label"] == "Robin"
