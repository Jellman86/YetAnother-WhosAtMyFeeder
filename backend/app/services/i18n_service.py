import json
from pathlib import Path
from typing import Dict, Any
import structlog

log = structlog.get_logger()

class I18nService:
    def __init__(self):
        self.translations: Dict[str, Dict[str, Any]] = {}
        self._load_translations()

    def _load_translations(self):
        # backend/app/services/i18n_service.py -> backend/locales
        locales_dir = Path(__file__).parent.parent.parent / "locales"
        for locale_file in locales_dir.glob("*.json"):
            lang = locale_file.stem
            try:
                with open(locale_file, 'r', encoding='utf-8') as f:
                    self.translations[lang] = json.load(f)
                log.info("loaded_translation", language=lang)
            except Exception as e:
                log.error("failed_to_load_translation", language=lang, error=str(e))

    def translate(self, key: str, lang: str = "en", **kwargs) -> str:
        """Get translated string with optional template variables."""
        # Split key by dot for nested dictionary access
        keys = key.split('.')
        
        # Try to get translation in requested language
        translation = self.translations.get(lang, {})
        for k in keys:
            if isinstance(translation, dict):
                translation = translation.get(k)
            else:
                translation = None
                break
        
        # Fallback to English if not found
        if not translation:
            translation = self.translations.get("en", {})
            for k in keys:
                if isinstance(translation, dict):
                    translation = translation.get(k)
                else:
                    translation = None
                    break
        
        # If still not found, return the key itself
        if not translation or not isinstance(translation, str):
            return key

        # Simple template replacement
        for k, v in kwargs.items():
            translation = translation.replace(f"{{{k}}}", str(v))

        return translation

i18n_service = I18nService()
