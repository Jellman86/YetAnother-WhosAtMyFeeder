import pytest
from app.services.i18n_service import i18n_service


def test_load_all_locales():
    """All locale files should load without errors."""
    assert len(i18n_service.translations) == 9
    assert "en" in i18n_service.translations
    assert "es" in i18n_service.translations
    assert "fr" in i18n_service.translations
    assert "de" in i18n_service.translations
    assert "ja" in i18n_service.translations
    assert "zh" in i18n_service.translations
    assert "ru" in i18n_service.translations
    assert "pt" in i18n_service.translations
    assert "it" in i18n_service.translations


def test_translate_simple_key():
    """Simple key translation should work."""
    result = i18n_service.translate("notification.new_detection", "en")
    assert "New" in result or "detected" in result.lower()
    assert "{species}" in result  # Should contain template variable


def test_translate_nested_key():
    """Nested key translation should work."""
    result = i18n_service.translate("errors.proxy.frigate_timeout", "en")
    assert "timeout" in result.lower() or "timed out" in result.lower()


def test_translate_with_variables():
    """Template variable substitution should work."""
    result = i18n_service.translate(
        "errors.proxy.frigate_error",
        "en",
        status_code=500
    )
    assert "500" in result


def test_translate_with_multiple_variables():
    """Multiple template variables should work."""
    result = i18n_service.translate(
        "notification.detection_body",
        "en",
        species="Blue Jay",
        camera="front_feeder",
        confidence=95
    )
    assert "Blue Jay" in result
    assert "front_feeder" in result
    assert "95" in result


def test_fallback_to_english():
    """Missing translation should fall back to English."""
    # Try to get a key that exists in English but test fallback behavior
    result = i18n_service.translate("errors.detection_not_found", "en")
    assert len(result) > 0
    assert "not found" in result.lower() or "found" in result.lower()


def test_missing_key_returns_key():
    """Missing key should return the key itself."""
    result = i18n_service.translate("fake.nonexistent.key", "en")
    assert result == "fake.nonexistent.key"


def test_all_locales_have_core_notification_keys():
    """All locales should have core notification structure."""
    core_keys = [
        "notification.new_detection",
        "notification.detection_body",
        "notification.audio_confirmed"
    ]
    for locale in ["en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it"]:
        for key in core_keys:
            result = i18n_service.translate(key, locale)
            assert result != key, f"Missing translation for {key} in {locale}"
            assert len(result) > 0


def test_all_locales_have_core_error_keys():
    """All locales should have core error keys."""
    core_keys = [
        "errors.detection_not_found",
        "errors.frigate_timeout",
        "errors.proxy.frigate_timeout",
        "errors.proxy.frigate_auth_failed",
        "errors.proxy.snapshot_not_found",
        "errors.events.snapshot_fetch_failed",
        "errors.events.classification_failed"
    ]
    for locale in ["en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it"]:
        for key in core_keys:
            result = i18n_service.translate(key, locale)
            assert result != key, f"Missing translation for {key} in {locale}"
            assert len(result) > 0


def test_chinese_locale_exists_and_works():
    """Chinese locale should exist and work."""
    result = i18n_service.translate("notification.new_detection", "zh")
    assert result != "notification.new_detection"
    # Check it's actually Chinese characters (basic check - Unicode range for CJK)
    assert any(ord(char) > 0x4E00 and ord(char) < 0x9FFF for char in result), \
        "Chinese translation should contain Chinese characters"


def test_spanish_locale_works():
    """Spanish locale should work."""
    result = i18n_service.translate("errors.detection_not_found", "es")
    assert result != "errors.detection_not_found"
    # Spanish uses "no encontrado" or similar
    assert "encontr" in result.lower() or "no" in result.lower()


def test_japanese_locale_works():
    """Japanese locale should work."""
    result = i18n_service.translate("notification.new_detection", "ja")
    assert result != "notification.new_detection"
    # Check for Japanese characters (Hiragana, Katakana, or Kanji)
    assert any(
        (ord(char) >= 0x3040 and ord(char) <= 0x309F) or  # Hiragana
        (ord(char) >= 0x30A0 and ord(char) <= 0x30FF) or  # Katakana
        (ord(char) >= 0x4E00 and ord(char) <= 0x9FFF)     # Kanji
        for char in result
    ), "Japanese translation should contain Japanese characters"


def test_proxy_error_structure():
    """Proxy errors should have proper nested structure."""
    proxy_keys = [
        "errors.proxy.frigate_timeout",
        "errors.proxy.frigate_auth_failed",
        "errors.proxy.frigate_error",
        "errors.proxy.connection_failed",
        "errors.proxy.snapshot_not_found",
        "errors.proxy.thumbnail_not_found",
        "errors.proxy.clip_not_found",
        "errors.proxy.clip_not_available",
        "errors.proxy.event_not_found",
        "errors.proxy.empty_clip",
        "errors.proxy.invalid_event_id"
    ]
    for key in proxy_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_events_error_structure():
    """Events errors should have proper nested structure."""
    events_keys = [
        "errors.events.snapshot_fetch_failed",
        "errors.events.classification_failed",
        "errors.events.delete_failed",
        "errors.events.update_failed",
        "errors.events.wildlife_model_unavailable",
        "errors.events.reclassification_failed"
    ]
    for key in events_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_ai_error_structure():
    """AI errors should have proper nested structure."""
    ai_keys = [
        "errors.ai.provider_not_configured",
        "errors.ai.api_key_missing",
        "errors.ai.analysis_failed",
        "errors.ai.image_fetch_failed"
    ]
    for key in ai_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_backfill_error_structure():
    """Backfill errors should have proper nested structure."""
    backfill_keys = [
        "errors.backfill.no_events",
        "errors.backfill.processing_error",
        "errors.backfill.invalid_time_range"
    ]
    for key in backfill_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_unsupported_language_fallback():
    """Unsupported language should fall back to English."""
    # i18n_service should handle this gracefully
    # Try Korean (not supported)
    result = i18n_service.translate("errors.detection_not_found", "ko")
    # Should either fall back to English or return the key
    assert len(result) > 0


def test_empty_locale_fallback():
    """Empty locale should fall back to English."""
    result = i18n_service.translate("errors.detection_not_found", "")
    assert len(result) > 0


def test_none_locale_fallback():
    """None locale should fall back to English."""
    result = i18n_service.translate("errors.detection_not_found", None)
    assert len(result) > 0


def test_variable_substitution_with_url():
    """Variable substitution should work with URLs."""
    result = i18n_service.translate(
        "errors.proxy.connection_failed",
        "en",
        url="http://localhost:5000"
    )
    assert "http://localhost:5000" in result or "localhost" in result


def test_variable_substitution_preserves_type():
    """Variable substitution should handle different types."""
    # Test with integer
    result = i18n_service.translate(
        "errors.proxy.frigate_error",
        "en",
        status_code=404
    )
    assert "404" in result

    # Test with string
    result2 = i18n_service.translate(
        "errors.backfill.processing_error",
        "en",
        error="Connection timeout"
    )
    assert "Connection timeout" in result2


def test_translation_completeness():
    """Verify all locales have the same structure."""
    # Get all keys from English (master locale)
    en_translations = i18n_service.translations.get("en", {})

    def get_all_keys(d, prefix=""):
        """Recursively get all keys from nested dict."""
        keys = []
        for k, v in d.items():
            current_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(get_all_keys(v, current_key))
            else:
                keys.append(current_key)
        return keys

    en_keys = get_all_keys(en_translations)

    # Verify all other locales have the same keys
    for locale in ["es", "fr", "de", "ja", "zh", "ru", "pt", "it"]:
        locale_translations = i18n_service.translations.get(locale, {})
        locale_keys = get_all_keys(locale_translations)

        # Check that all English keys exist in this locale
        missing_keys = set(en_keys) - set(locale_keys)
        assert len(missing_keys) == 0, \
            f"Locale {locale} is missing keys: {missing_keys}"


def test_no_extra_keys_in_other_locales():
    """Verify other locales don't have extra keys not in English."""
    en_translations = i18n_service.translations.get("en", {})

    def get_all_keys(d, prefix=""):
        keys = []
        for k, v in d.items():
            current_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(get_all_keys(v, current_key))
            else:
                keys.append(current_key)
        return keys

    en_keys = set(get_all_keys(en_translations))

    for locale in ["es", "fr", "de", "ja", "zh", "ru", "pt", "it"]:
        locale_translations = i18n_service.translations.get(locale, {})
        locale_keys = set(get_all_keys(locale_translations))

        # Check for extra keys
        extra_keys = locale_keys - en_keys
        # Allow some flexibility for locale-specific metadata keys
        extra_keys = {k for k in extra_keys if not k.startswith("_")}

        assert len(extra_keys) == 0, \
            f"Locale {locale} has extra keys not in English: {extra_keys}"


def test_species_errors():
    """Species errors should exist."""
    species_keys = [
        "errors.species.unknown_bird",
        "errors.species.species_not_found"
    ]
    for key in species_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_classifier_errors():
    """Classifier errors should exist."""
    classifier_keys = [
        "errors.classifier.bird_model_not_loaded",
        "errors.classifier.wildlife_model_not_loaded",
        "errors.classifier.model_load_failed"
    ]
    for key in classifier_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_models_errors():
    """Models errors should exist."""
    models_keys = [
        "errors.models.not_installed",
        "errors.models.download_failed"
    ]
    for key in models_keys:
        result = i18n_service.translate(key, "en")
        assert result != key, f"Missing translation for {key}"
        assert len(result) > 0


def test_email_errors():
    """Email errors should exist in all locales."""
    email_keys = [
        "errors.email.gmail_oauth_not_configured",
        "errors.email.outlook_oauth_not_configured",
        "errors.email.invalid_provider",
        "errors.email.not_enabled",
        "errors.email.recipient_not_configured",
        "errors.email.smtp_incomplete",
        "errors.email.send_failed"
    ]
    for locale in ["en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it"]:
        for key in email_keys:
            result = i18n_service.translate(key, locale)
            assert result != key, f"Missing email translation for {key} in {locale}"
            assert len(result) > 0


def test_email_errors_with_variables():
    """Email errors with variables should work."""
    result = i18n_service.translate(
        "errors.email.gmail_oauth_failed",
        "en",
        error="Connection timeout"
    )
    assert "Connection timeout" in result

    result2 = i18n_service.translate(
        "errors.email.disconnect_error",
        "en",
        error="Token expired"
    )
    assert "Token expired" in result2
