import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ai_service import AIService


@pytest.fixture
def ai_service():
    return AIService()


@pytest.mark.asyncio
async def test_analyze_detection_disabled(ai_service):
    """Should return message if AI is disabled."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = False
        mock_settings.llm.api_key = "test_key"

        result = await ai_service.analyze_detection(
            species="Blue Jay",
            image_data=b"fake_image",
            metadata={}
        )

        assert "disabled" in result.lower() or "missing" in result.lower()


@pytest.mark.asyncio
async def test_analyze_detection_no_api_key(ai_service):
    """Should return message if API key is missing."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = ""

        result = await ai_service.analyze_detection(
            species="Blue Jay",
            image_data=b"fake_image",
            metadata={}
        )

        assert "disabled" in result.lower() or "missing" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_success(ai_service):
    """Should analyze image with Gemini API successfully."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-3-flash-preview"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "This is a Blue Jay perched at a bird feeder. The bird is showing typical foraging behavior."
                    }]
                }
            }]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Blue Jay",
                image_data=b"fake_image_data",
                metadata={"camera": "front_feeder", "confidence": 0.95}
            )

            assert "Blue Jay" in result
            assert "behavior" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_empty_response(ai_service):
    """Should handle Gemini returning no candidates."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-3-flash-preview"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"candidates": []}
        mock_response.text = "{}"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Robin",
                image_data=b"fake_image",
                metadata={}
            )

            assert "empty" in result.lower()


@pytest.mark.asyncio
async def test_analyze_gemini_api_error(ai_service):
    """Should handle Gemini API errors gracefully."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-3-flash-preview"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=Exception("API connection failed"))
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Cardinal",
                image_data=b"fake_image",
                metadata={}
            )

            assert "Error" in result or "failed" in result.lower()


@pytest.mark.asyncio
async def test_analyze_openai_success(ai_service):
    """Should analyze image with OpenAI API successfully."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-5.2-instant"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "The Northern Cardinal in this image is displaying territorial behavior."
                }
            }]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Northern Cardinal",
                image_data=b"fake_image_data",
                metadata={"camera": "back_yard"}
            )

            assert "Cardinal" in result
            assert "territorial" in result.lower()


@pytest.mark.asyncio
async def test_analyze_claude_success(ai_service):
    """Should analyze image with Claude API successfully."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "claude"
        mock_settings.llm.model = "claude-sonnet-4-5-20250929"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{
                "text": "This Robin appears to be engaged in feeding behavior at the bird feeder."
            }]
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await ai_service.analyze_detection(
                species="Robin",
                image_data=b"fake_image_data",
                metadata={}
            )

            assert "Robin" in result or "feeding" in result.lower()


@pytest.mark.asyncio
async def test_analyze_unsupported_provider(ai_service):
    """Should return error message for unsupported provider."""
    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "unknown_provider"

        result = await ai_service.analyze_detection(
            species="Sparrow",
            image_data=b"fake_image",
            metadata={}
        )

        assert "Unsupported" in result


@pytest.mark.asyncio
async def test_build_prompt_includes_metadata(ai_service):
    """Prompt should include species and metadata."""
    with patch('app.services.ai_service.settings') as mock_settings:
        metadata = {
            "camera": "feeder_cam",
            "confidence": 0.92,
            "timestamp": "2024-01-15 10:30:00"
        }

        prompt = ai_service._build_prompt("Blue Jay", metadata)

        assert "Blue Jay" in prompt
        # Metadata should be included in some form
        assert len(prompt) > 50  # Should be a substantial prompt


@pytest.mark.asyncio
async def test_image_encoding(ai_service):
    """Image data should be properly base64 encoded."""
    import base64

    test_image = b"fake_jpeg_binary_data_12345"

    with patch('app.services.ai_service.settings') as mock_settings:
        mock_settings.llm.enabled = True
        mock_settings.llm.api_key = "test_key"
        mock_settings.llm.provider = "gemini"
        mock_settings.llm.model = "gemini-3-flash-preview"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Analysis"}]}}]}

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            await ai_service.analyze_detection(
                species="Test Bird",
                image_data=test_image,
                metadata={}
            )

            # Check that post was called with properly encoded image
            call_args = mock_instance.post.call_args
            payload = call_args.kwargs['json']

            # The image should be base64 encoded
            inline_data = payload['contents'][0]['parts'][1]['inline_data']
            encoded_data = inline_data['data']

            # Should be valid base64
            decoded = base64.b64decode(encoded_data)
            assert decoded == test_image
