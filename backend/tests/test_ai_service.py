import base64

import cv2
import httpx
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ai_service import AIAnalysisError, AIService


@pytest.fixture
def ai_service():
    return AIService()


@pytest.mark.asyncio
async def test_analyze_detection_disabled(ai_service):
    """Should return message if AI is disabled."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = False
        mock_settings.llm.api_key = "test_key"

        result = await ai_service.analyze_detection(species="Blue Jay", image_data=b"fake_image", metadata={})

        assert "disabled" in result.lower() or "missing" in result.lower()


@pytest.mark.asyncio
async def test_analyze_detection_no_api_key(ai_service):
    """Should return message if API key is missing."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = ""

        result = await ai_service.analyze_detection(species="Blue Jay", image_data=b"fake_image", metadata={})

        assert "disabled" in result.lower() or "missing" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_success(ai_service):
    """Should analyze image with Gemini API successfully."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-2.5-flash"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "This is a Blue Jay perched at a bird feeder. The bird is showing typical foraging behavior."
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Blue Jay",
                image_data=b"fake_image_data",
                metadata={"camera": "front_feeder", "confidence": 0.95},
            )

            assert "Blue Jay" in result
            assert "behavior" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_empty_response(ai_service):
    """Should handle Gemini returning no candidates."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-2.5-flash"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"candidates": []}
        mock_response.text = "{}"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(species="Robin", image_data=b"fake_image", metadata={})

            assert "empty" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_api_error(ai_service):
    """Should handle Gemini API errors gracefully."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-2.5-flash"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            # __aexit__ must return None/False to propagate exceptions
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(side_effect=Exception("API connection failed"))
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(species="Cardinal", image_data=b"fake_image", metadata={})

            assert result is not None
            assert "Error" in result or "failed" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_error_does_not_expose_query_string_api_key(ai_service):
    secret = "gemini-secret-key"
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = secret
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-vision"

        request = httpx.Request(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-vision:generateContent?key={secret}",
        )
        response = httpx.Response(503, request=request)
        error = httpx.HTTPStatusError(f"503 for {request.url}", request=request, response=response)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(side_effect=error)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(species="Cardinal", image_data=b"fake_image", metadata={})

    assert secret not in result
    assert "***REDACTED***" in result


@pytest.mark.asyncio
async def test_analyze_openai_success(ai_service):
    """Should analyze image with OpenAI API successfully."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-5.2-instant"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "The Northern Cardinal in this image is displaying territorial behavior."}}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Northern Cardinal", image_data=b"fake_image_data", metadata={"camera": "back_yard"}
            )

            assert "Cardinal" in result
            assert "territorial" in result.lower()


@pytest.mark.asyncio
async def test_analyze_claude_success(ai_service):
    """Should analyze image with Claude API successfully."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "claude"
        mock_settings.llm.model = "claude-sonnet-4-5-20250929"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"text": "This Robin appears to be engaged in feeding behavior at the bird feeder."}]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(species="Robin", image_data=b"fake_image_data", metadata={})

            assert "Robin" in result or "feeding" in result.lower()


@pytest.mark.asyncio
async def test_analyze_unsupported_provider(ai_service):
    """Should return error message for unsupported provider."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "unknown_provider"

        result = await ai_service.analyze_detection(species="Sparrow", image_data=b"fake_image", metadata={})

        assert "Unsupported" in result


@pytest.mark.asyncio
async def test_build_prompt_includes_metadata(ai_service):
    """Prompt should include species and metadata."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.analysis_prompt_template = "Species identified by system: {species}\nTime: {time}"
        metadata = {"camera": "feeder_cam", "confidence": 0.92, "timestamp": "2024-01-15 10:30:00"}

        prompt = ai_service._build_prompt("Blue Jay", metadata)

        assert "Blue Jay" in prompt
        # Metadata should be included in some form
        assert len(prompt) > 50  # Should be a substantial prompt


@pytest.mark.asyncio
async def test_build_prompt_describes_recording_clip_frames(ai_service):
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.analysis_prompt_template = "{frame_note}"

        prompt = ai_service._build_prompt(
            "Robin",
            {"frame_count": 5, "frame_source": "recording"},
        )

        assert "full-visit clip" in prompt


def test_extract_frames_from_clip_accepts_recording_variant(ai_service):
    with patch("app.services.ai_service.cv2.VideoCapture") as mock_capture:
        capture = MagicMock()
        capture.get.side_effect = [20]
        capture.read.return_value = (False, None)
        mock_capture.return_value = capture

        frames = ai_service.extract_frames_from_clip(b"clip-bytes", frame_count=5, clip_variant="recording")

        assert frames == []


@pytest.mark.asyncio
async def test_image_encoding(ai_service):
    """Image data should be properly base64 encoded."""
    import base64

    test_image = b"fake_jpeg_binary_data_12345"

    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-2.5-flash"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Analysis"}]}}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            await ai_service.analyze_detection(species="Test Bird", image_data=test_image, metadata={})

            # Check that post was called with properly encoded image
            call_args = mock_instance.post.call_args
            payload = call_args.kwargs["json"]

            # The image should be base64 encoded
            inline_data = payload["contents"][0]["parts"][1]["inline_data"]
            encoded_data = inline_data["data"]

            # Should be valid base64
            decoded = base64.b64decode(encoded_data)
            assert decoded == test_image


@pytest.mark.asyncio
async def test_analyze_openrouter_success(ai_service):
    """Should analyze image via OpenRouter (OpenAI-compatible) successfully."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "sk-or-test"
        mock_settings.llm.provider = "openrouter"
        mock_settings.llm.model = "google/gemini-2.5-flash"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This House Sparrow is foraging at the feeder."}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="House Sparrow", image_data=b"fake_image_data", metadata={"camera": "front_yard"}
            )

            assert "Sparrow" in result or "foraging" in result.lower()

            # Should call the OpenRouter endpoint
            call_args = mock_instance.post.call_args
            assert "openrouter.ai" in call_args.args[0]


@pytest.mark.asyncio
async def test_test_connection_openrouter_success(ai_service):
    """test_connection should return True for a valid OpenRouter key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(
            provider="openrouter", model="google/gemini-2.5-flash", api_key="sk-or-test"
        )

        assert result.ok is True
        call_args = mock_instance.post.call_args
        assert "openrouter.ai" in call_args.args[0]


@pytest.mark.asyncio
async def test_test_connection_openrouter_empty_response(ai_service):
    """test_connection should return False when OpenRouter returns no choices."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": []}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(
            provider="openrouter", model="google/gemini-2.5-flash", api_key="sk-or-test"
        )

        assert result.ok is False
        assert result.failure_stage == "response"


def test_describe_http_error_is_actionable():
    describe = AIService._describe_http_error
    assert "rate-limited" in describe(429, "busy/model", "").lower()
    assert "key" in describe(401, "m", "").lower()
    assert "credit" in describe(402, "m", "").lower()
    assert "not found" in describe(404, "m", "").lower()


def test_diagnostic_frame_matches_representative_production_dimensions():
    encoded = base64.b64decode(AIService._test_probe_frame_b64())
    frame = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert frame is not None
    assert frame.shape[:2] == (AIService.TEST_PROBE_FRAME_HEIGHT, AIService.TEST_PROBE_FRAME_WIDTH)
    assert len(encoded) > 500_000


@pytest.mark.asyncio
async def test_test_connection_sends_a_vision_probe(ai_service):
    """The connection test sends an image so it exercises the same vision path a real analysis uses."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(
            provider="openrouter", model="some/vision-model", api_key="sk-or-test"
        )

    assert result.ok is True
    parts = mock_instance.post.call_args.kwargs["json"]["messages"][0]["content"]
    image_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "image_url"]
    assert len(image_parts) == AIService.TEST_PROBE_FRAME_COUNT
    assert all(p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in image_parts)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "response_payload"),
    [
        ("gemini", {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}),
        ("openai", {"choices": [{"message": {"content": "OK"}}]}),
        ("claude", {"content": [{"text": "OK"}]}),
    ],
)
async def test_test_connection_uses_five_jpeg_frames_for_each_provider(ai_service, provider, response_payload):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = response_payload

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(provider=provider, model="vision-model", api_key="test-key")

    assert result.ok is True
    payload = mock_instance.post.call_args.kwargs["json"]
    if provider == "gemini":
        image_parts = [part for part in payload["contents"][0]["parts"] if "inline_data" in part]
        assert len(image_parts) == AIService.TEST_PROBE_FRAME_COUNT
        assert all(part["inline_data"]["mime_type"] == "image/jpeg" for part in image_parts)
    elif provider == "claude":
        image_parts = [part for part in payload["messages"][0]["content"] if part.get("type") == "image"]
        assert len(image_parts) == AIService.TEST_PROBE_FRAME_COUNT
        assert all(part["source"]["media_type"] == "image/jpeg" for part in image_parts)
    else:
        image_parts = [part for part in payload["messages"][0]["content"] if part.get("type") == "image_url"]
        assert len(image_parts) == AIService.TEST_PROBE_FRAME_COUNT
        assert all(part["image_url"]["url"].startswith("data:image/jpeg;base64,") for part in image_parts)


def _provider_error(status: int, message: str, *, retry_after: int | None = None) -> httpx.HTTPStatusError:
    """Build the real httpx error shape used by provider responses."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    response = httpx.Response(status, json={"error": {"message": message}}, headers=headers, request=request)
    return httpx.HTTPStatusError(str(status), request=request, response=response)


def _rate_limit_error() -> httpx.HTTPStatusError:
    return _provider_error(429, "rate-limited upstream", retry_after=60)


@pytest.mark.asyncio
async def test_test_connection_surfaces_rate_limit(ai_service):
    """A 429 from the provider is reported as a rate limit with a 429 hint, not a generic failure."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(side_effect=_rate_limit_error())
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(provider="openrouter", model="busy/model", api_key="sk-or-test")

    assert result.ok is False
    assert result.http_status_hint == 429
    assert result.failure_stage == "provider"
    assert result.retryable is True
    assert result.retry_after_seconds == 60
    assert "rate-limited" in result.message.lower()


@pytest.mark.asyncio
async def test_test_connection_surfaces_transient_provider_unavailability(ai_service):
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(
            side_effect=_provider_error(503, "No available provider meets the routing requirements", retry_after=15)
        )
        mock_client.return_value = mock_instance

        result = await ai_service.test_connection(provider="openrouter", model="busy/model", api_key="sk-or-test")

    assert result.ok is False
    assert result.http_status_hint == 503
    assert result.failure_stage == "provider"
    assert result.retryable is True
    assert result.retry_after_seconds == 15
    assert "retry" in result.message.lower()


@pytest.mark.asyncio
async def test_openrouter_analysis_surfaces_rate_limit(ai_service):
    """A 429 during a real analysis returns the actionable rate-limit message, not a raw error."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "sk-or-test"
        mock_settings.llm.provider = "openrouter"
        mock_settings.llm.model = "busy/model"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(side_effect=_rate_limit_error())
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(species="Blue Jay", image_data=b"fakeimage", metadata={})

    assert result is not None
    assert isinstance(result, AIAnalysisError)
    assert result.http_status_hint == 429
    assert result.retryable is True
    assert result.retry_after_seconds == 60
    assert "rate-limited" in result.lower()
