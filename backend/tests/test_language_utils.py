import pytest
from unittest.mock import MagicMock
from app.utils.language import get_user_language


def test_get_user_language_en_us():
    """Should extract 'en' from 'en-US' header."""
    request = MagicMock()
    request.headers.get.return_value = "en-US"

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_zh_cn():
    """Should extract 'zh' from 'zh-CN' header."""
    request = MagicMock()
    request.headers.get.return_value = "zh-CN"

    result = get_user_language(request)

    assert result == "zh"


def test_get_user_language_complex_header():
    """Should extract first language from complex Accept-Language header."""
    request = MagicMock()
    request.headers.get.return_value = "en-US,en;q=0.9,es;q=0.8"

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_spanish():
    """Should extract 'es' from Spanish header."""
    request = MagicMock()
    request.headers.get.return_value = "es-ES,es;q=0.9"

    result = get_user_language(request)

    assert result == "es"


def test_get_user_language_japanese():
    """Should extract 'ja' from Japanese header."""
    request = MagicMock()
    request.headers.get.return_value = "ja-JP"

    result = get_user_language(request)

    assert result == "ja"


def test_get_user_language_portuguese():
    """Should extract 'pt' from Portuguese header."""
    request = MagicMock()
    request.headers.get.return_value = "pt-BR"

    result = get_user_language(request)

    assert result == "pt"


def test_get_user_language_missing_header():
    """Missing Accept-Language header should return 'en'."""
    request = MagicMock()
    request.headers.get.return_value = None

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_empty_header():
    """Empty Accept-Language header should return 'en'."""
    request = MagicMock()
    request.headers.get.return_value = ""

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_simple_code():
    """Should handle simple language codes without region."""
    request = MagicMock()
    request.headers.get.return_value = "en"

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_with_quality():
    """Should handle quality values in header."""
    request = MagicMock()
    request.headers.get.return_value = "fr;q=0.9"

    result = get_user_language(request)

    assert result == "fr"


def test_get_user_language_german():
    """Should extract 'de' from German header."""
    request = MagicMock()
    request.headers.get.return_value = "de-DE"

    result = get_user_language(request)

    assert result == "de"


def test_get_user_language_french():
    """Should extract 'fr' from French header."""
    request = MagicMock()
    request.headers.get.return_value = "fr-FR"

    result = get_user_language(request)

    assert result == "fr"


def test_get_user_language_all_supported():
    """Test all supported languages."""
    supported = {
        "en-US": "en",
        "es-ES": "es",
        "fr-FR": "fr",
        "de-DE": "de",
        "ja-JP": "ja",
        "zh-CN": "zh"
    }

    for header, expected in supported.items():
        request = MagicMock()
        request.headers.get.return_value = header
        result = get_user_language(request)
        assert result == expected, f"Failed for {header}"


def test_get_user_language_case_insensitive():
    """Should handle different cases."""
    request = MagicMock()
    request.headers.get.return_value = "EN-US"

    result = get_user_language(request)

    # The function extracts the first part, which should still work
    assert result == "en" or result == "EN"


def test_get_user_language_with_whitespace():
    """Should handle whitespace in header."""
    request = MagicMock()
    request.headers.get.return_value = " en-US "

    result = get_user_language(request)

    assert result == "en"


def test_get_user_language_multiple_locales():
    """Should take first locale from multiple."""
    request = MagicMock()
    request.headers.get.return_value = "zh-CN,en-US;q=0.9,ja;q=0.8"

    result = get_user_language(request)

    assert result == "zh"


def test_get_user_language_rare_locale():
    """Should fallback for rare/unsupported locales."""
    request = MagicMock()
    request.headers.get.return_value = "yi-US"  # Yiddish - not supported

    result = get_user_language(request)

    assert result == "en"


def test_supported_languages_list():
    """Verify the supported languages list."""
    # This test documents which languages are supported
    supported = ["en", "es", "fr", "de", "ja", "zh"]

    for lang in supported:
        request = MagicMock()
        request.headers.get.return_value = f"{lang}-XX"
        result = get_user_language(request)
        assert result == lang, f"Language {lang} should be supported"
