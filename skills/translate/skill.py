"""
Translate skill - translate text between languages.

Uses pattern-based language detection for common languages and
formats the translation request for the AI model to handle.
"""

# Common language codes and names
LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "tr": "Turkish",
    "vi": "Vietnamese", "th": "Thai", "uk": "Ukrainian", "cs": "Czech",
    "ro": "Romanian", "da": "Danish", "fi": "Finnish", "el": "Greek",
    "he": "Hebrew", "id": "Indonesian", "ms": "Malay", "no": "Norwegian",
    "bn": "Bengali", "ta": "Tamil",
}

# Reverse lookup: name -> code
NAME_TO_CODE = {v.lower(): k for k, v in LANGUAGES.items()}


def run(args: str, context: dict) -> str:
    """Translate text. Args format: <target_lang> <text> or just <text> (defaults to English)."""
    if not args.strip():
        return "Usage: /skill translate run <text> or /skill translate to <lang> <text>"
    # Try to parse "to <lang>" prefix
    parts = args.strip().split(None, 2)
    if parts[0].lower() == "to" and len(parts) >= 2:
        lang = parts[1]
        text = parts[2] if len(parts) > 2 else ""
        if not text:
            messages = context.get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
        return _format_translation(text, lang)
    # Default: translate to English
    return _format_translation(args.strip(), "en")


def to_lang(args: str, context: dict) -> str:
    """Translate to a specific language."""
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return "Usage: /skill translate to <language> <text>"
    lang = parts[0]
    text = parts[1]
    return _format_translation(text, lang)


def detect(args: str, context: dict) -> str:
    """Detect the language of the provided text."""
    text = args.strip()
    if not text:
        messages = context.get("messages", [])
        if messages:
            text = messages[-1].get("content", "")
    if not text:
        return "No text provided."
    detected = _detect_language(text)
    return f"Detected language: {detected}"


def _format_translation(text: str, target_lang: str) -> str:
    """Format a translation request for the AI model."""
    lang_name = _resolve_lang_name(target_lang)
    detected = _detect_language(text)
    return (
        f"[Translation Request]\n"
        f"Source language: {detected}\n"
        f"Target language: {lang_name}\n"
        f"Text to translate: {text}\n\n"
        f"Please translate the above text from {detected} to {lang_name}. "
        f"Provide only the translation, preserving formatting."
    )


def _resolve_lang_name(lang: str) -> str:
    """Resolve a language code or name to a full name."""
    lang_lower = lang.lower().strip()
    if lang_lower in LANGUAGES:
        return LANGUAGES[lang_lower]
    if lang_lower in NAME_TO_CODE:
        return LANGUAGES[NAME_TO_CODE[lang_lower]]
    return lang  # Return as-is if unknown


def _detect_language(text: str) -> str:
    """Simple pattern-based language detection."""
    # Character range heuristics
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in text)
    has_hiragana = any("\u3040" <= c <= "\u309f" for c in text)
    has_katakana = any("\u30a0" <= c <= "\u30ff" for c in text)
    has_cyrillic = any("\u0400" <= c <= "\u04ff" for c in text)
    has_arabic = any("\u0600" <= c <= "\u06ff" for c in text)
    has_devanagari = any("\u0900" <= c <= "\u097f" for c in text)
    has_hangul = any("\uac00" <= c <= "\ud7af" for c in text)

    if has_cjk and not has_hiragana and not has_katakana:
        return "Chinese"
    if has_hiragana or has_katakana:
        return "Japanese"
    if has_hangul:
        return "Korean"
    if has_cyrillic:
        return "Russian"
    if has_arabic:
        return "Arabic"
    if has_devanagari:
        return "Hindi"
    # Latin script - default to English
    return "English"
