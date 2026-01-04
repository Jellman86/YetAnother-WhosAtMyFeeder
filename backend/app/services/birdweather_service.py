import httpx
import structlog
from datetime import datetime
from typing import Optional
from app.config import settings

log = structlog.get_logger()

class BirdWeatherService:
    def __init__(self):
        self.api_url = "https://app.birdweather.com/api/v1"

    async def report_detection(
        self,
        scientific_name: str,
        common_name: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp: Optional[datetime] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        token: Optional[str] = None
    ) -> bool:
        """Report a detection to BirdWeather."""
        # If token is provided (testing), ignore enabled check. Otherwise require enabled + token.
        active_token = token or settings.birdweather.station_token
        if not active_token:
            return False
            
        if token is None and not settings.birdweather.enabled:
            return False

        url = f"{self.api_url}/stations/{active_token}/detections"
        
        # Format timestamp as ISO8601
        ts = timestamp or datetime.now()
        ts_iso = ts.isoformat()

        payload = {
            "timestamp": ts_iso,
            "scientificName": scientific_name,
            "commonName": common_name or scientific_name,
        }

        if confidence is not None:
            payload["confidence"] = confidence
        
        # Use location from params or fallback to settings
        lat = latitude or settings.location.latitude
        lon = longitude or settings.location.longitude
        
        if lat is not None and lon is not None:
            payload["lat"] = lat
            payload["lon"] = lon

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                log.info("Reported detection to BirdWeather", 
                         species=scientific_name, 
                         status=resp.status_code)
                return True
        except Exception as e:
            log.error("Failed to report detection to BirdWeather", 
                      species=scientific_name, 
                      error=str(e))
            return False

birdweather_service = BirdWeatherService()
