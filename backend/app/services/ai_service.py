import httpx
import structlog
import base64
from typing import Optional
from app.config import settings

log = structlog.get_logger()

class AIService:
    """Service to interact with LLMs for behavioral analysis."""

    async def analyze_detection(self, species: str, image_data: bytes,
                                metadata: dict) -> Optional[str]:
        """Send image and metadata to LLM for analysis."""
        if not settings.llm.enabled or not settings.llm.api_key:
            return "AI Analysis is disabled or API key is missing."

        if settings.llm.provider == "gemini":
            return await self._analyze_gemini(species, image_data, metadata)
        elif settings.llm.provider == "openai":
            return await self._analyze_openai(species, image_data, metadata)
        elif settings.llm.provider == "claude":
            return await self._analyze_claude(species, image_data, metadata)

        return "Unsupported AI provider."

    async def _analyze_gemini(self, species: str, image_data: bytes, metadata: dict) -> Optional[str]:
        """Analyze using Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm.model}:generateContent?key={settings.llm.api_key}"
        
        prompt = self._build_prompt(species, metadata)
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 1024,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                
                # Extract text from response
                candidates = resp.json().get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text")
                
                log.warning("Gemini returned no candidates", response=resp.text)
                return "AI returned an empty response."
        except Exception as e:
            log.error("Gemini analysis failed", error=str(e))
            return f"Error during AI analysis: {str(e)}"

    async def _analyze_openai(self, species: str, image_data: bytes, metadata: dict) -> Optional[str]:
        """Analyze using OpenAI API (GPT-4o)."""
        url = "https://api.openai.com/v1/chat/completions"
        
        prompt = self._build_prompt(species, metadata)
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {settings.llm.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.llm.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content")
                
                return "AI returned an empty response."
        except Exception as e:
            log.error("OpenAI analysis failed", error=str(e))
            return f"Error during AI analysis: {str(e)}"

    async def _analyze_claude(self, species: str, image_data: bytes, metadata: dict) -> Optional[str]:
        """Analyze using Anthropic Claude API."""
        url = "https://api.anthropic.com/v1/messages"

        prompt = self._build_prompt(species, metadata)
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        headers = {
            "x-api-key": settings.llm.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.llm.model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

                content = data.get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text")

                return "AI returned an empty response."
        except Exception as e:
            log.error("Claude analysis failed", error=str(e))
            return f"Error during AI analysis: {str(e)}"

    def _build_prompt(self, species: str, metadata: dict) -> str:
        """Construct the prompt for the LLM."""
        temp = metadata.get("temperature")
        condition = metadata.get("weather_condition")
        time = metadata.get("time")
        
        weather_str = ""
        if temp is not None:
            weather_str = f"The weather is currently {temp}°C and {condition or 'clear'}."

        return f"""
        You are an expert ornithologist and naturalist. 
        I am showing you a snapshot of a bird detected at my feeder.
        
        Species identified by system: {species}
        Time of detection: {time or 'Unknown'}
        {weather_str}
        
        Please analyze this image and provide:
        1. A brief description of the bird's appearance in this specific snapshot.
        2. Any interesting behaviors you observe (e.g. feeding, alert, interacting with others).
        3. A 'Naturalist Note': a fun or educational fact about this species or its behavior in this context.
        
        Keep your response concise (under 200 words) and informative.
        """

ai_service = AIService()
