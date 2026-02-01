import httpx
import structlog
import base64
from typing import Optional
import tempfile
import cv2
import numpy as np
from app.config import settings

log = structlog.get_logger()

class AIService:
    """Service to interact with LLMs for behavioral analysis."""

    async def analyze_detection(
        self,
        species: str,
        image_data: Optional[bytes],
        metadata: dict,
        image_list: Optional[list[bytes]] = None,
        language: Optional[str] = None,
        mime_type: str = "image/jpeg"
    ) -> Optional[str]:
        """Send image(s) and metadata to LLM for analysis."""
        if not settings.llm.enabled or not settings.llm.api_key:
            return "AI Analysis is disabled or API key is missing."

        images = [(img, mime_type) for img in (image_list or []) if img]
        if not images and image_data:
            images = [(image_data, mime_type)]
        if not images:
            return "No image data available for AI analysis."

        prompt = self._build_prompt(species, metadata, language)
        if settings.llm.provider == "gemini":
            return await self._analyze_gemini_prompt(prompt, images)
        elif settings.llm.provider == "openai":
            return await self._analyze_openai_prompt(prompt, images)
        elif settings.llm.provider == "claude":
            return await self._analyze_claude_prompt(prompt, images)

        return "Unsupported AI provider."

    async def analyze_chart(self, image_data: bytes, metadata: dict, language: Optional[str] = None, mime_type: str = "image/png") -> Optional[str]:
        """Analyze a leaderboard chart image for trends."""
        if not settings.llm.enabled or not settings.llm.api_key:
            return "AI Analysis is disabled or API key is missing."
        if not image_data:
            return "No image data available for AI analysis."

        prompt = self._build_chart_prompt(metadata, language)
        images = [(image_data, mime_type)]

        if settings.llm.provider == "gemini":
            return await self._analyze_gemini_prompt(prompt, images)
        elif settings.llm.provider == "openai":
            return await self._analyze_openai_prompt(prompt, images)
        elif settings.llm.provider == "claude":
            return await self._analyze_claude_prompt(prompt, images)

        return "Unsupported AI provider."

    async def _analyze_gemini_prompt(self, prompt: str, images: list[tuple[bytes, str]]) -> Optional[str]:
        """Analyze using Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm.model}:generateContent?key={settings.llm.api_key}"
        
        parts = [{"text": prompt}]
        for image_data, mime_type in images:
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_base64
                }
            })

        payload = {
            "contents": [
                {
                    "parts": parts
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

    async def _analyze_openai_prompt(self, prompt: str, images: list[tuple[bytes, str]]) -> Optional[str]:
        """Analyze using OpenAI API (GPT-4o)."""
        url = "https://api.openai.com/v1/chat/completions"
        
        content = [{"type": "text", "text": prompt}]
        for image_data, mime_type in images:
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}"
                }
            })

        headers = {
            "Authorization": f"Bearer {settings.llm.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.llm.model,
            "messages": [
                {
                    "role": "user",
                    "content": content
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

    async def _analyze_claude_prompt(self, prompt: str, images: list[tuple[bytes, str]]) -> Optional[str]:
        """Analyze using Anthropic Claude API."""
        url = "https://api.anthropic.com/v1/messages"

        content = []
        for image_data, mime_type in images:
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": image_base64
                }
            })
        content.append({
            "type": "text",
            "text": prompt
        })

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
                    "content": content
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

    def _build_prompt(self, species: str, metadata: dict, language: Optional[str] = None) -> str:
        """Construct the prompt for the LLM."""
        temp = metadata.get("temperature")
        condition = metadata.get("weather_condition")
        time = metadata.get("time")
        frame_count = metadata.get("frame_count")
        frame_note = ""
        if frame_count:
            frame_note = f"I am showing you {frame_count} sequential frames from a short video clip."
        
        weather_str = ""
        if temp is not None:
            weather_str = f"The weather is currently {temp}°C and {condition or 'clear'}."

        language_note = f"Respond in {language}." if language else ""

        return f"""
        You are an expert ornithologist and naturalist.
        {frame_note if frame_note else "I am showing you a snapshot of a bird detected at my feeder."}

        Species identified by system: {species}
        Time of detection: {time or 'Unknown'}
        {weather_str}

        Respond in simple Markdown with these exact section headings and short bullet points:
        ## Appearance
        ## Behavior
        ## Naturalist Note
        ## Seasonal Context

        Keep the response concise (under 200 words). No extra sections.
        {language_note}
        """

    def _build_chart_prompt(self, metadata: dict, language: Optional[str] = None) -> str:
        """Construct a prompt for leaderboard trend analysis."""
        timeframe = metadata.get("timeframe", "Unknown timeframe")
        total_count = metadata.get("total_count", "unknown")
        series = ", ".join(metadata.get("series", [])) or "Detections"
        weather_notes = metadata.get("weather_notes", "")
        sunrise_range = metadata.get("sunrise_range")
        sunset_range = metadata.get("sunset_range")
        sun_notes = ""
        if sunrise_range or sunset_range:
            sun_notes = f"Sunrise range: {sunrise_range or 'unknown'}; Sunset range: {sunset_range or 'unknown'}."
        notes = metadata.get("notes", "")
        language_note = f"Respond in {language}." if language else ""
        return f"""
        You are a data analyst for bird feeder activity.
        You are looking at a chart of detections over time.

        Timeframe: {timeframe}
        Total detections in range: {total_count}
        Series shown: {series}
        {weather_notes}
        {sun_notes}

        Respond in Markdown with these exact section headings and short bullet points:
        ## Overview
        ## Patterns
        ## Weather Correlations
        ## Notable Spikes/Dips
        ## Caveats

        Keep it concise (under 200 words). No extra sections.
        {language_note}
        {notes}
        """

    def extract_frames_from_clip(self, clip_bytes: bytes, frame_count: int = 5) -> list[bytes]:
        """Extract a set of frames from a video clip, focused around the middle."""
        if not clip_bytes:
            return []
        frames: list[bytes] = []
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            tmp.write(clip_bytes)
            tmp.flush()
            cap = cv2.VideoCapture(tmp.name)
            try:
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames <= 0:
                    return []
                frame_count = max(1, min(frame_count, total_frames))
                center = total_frames / 2
                window = max(frame_count, int(total_frames * 0.4))
                start = max(0, int(center - window / 2))
                end = min(total_frames - 1, int(center + window / 2))
                indices = np.linspace(start, end, frame_count).astype(int)
                indices = np.clip(indices, 0, total_frames - 1)
                for idx in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        continue
                    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    if ok:
                        frames.append(buf.tobytes())
            finally:
                cap.release()
        return frames

ai_service = AIService()
