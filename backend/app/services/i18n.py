"""Localisation for citizen-facing copy.

Alerts are useless if the person receiving them cannot read them, so every
outbound message is rendered in the recipient's language. The MVP ships
English, Hindi and Garhwali (Devanagari); the catalog is data, so adding
Kumaoni or Nepali is a dictionary edit rather than a code change.
"""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGS = ("en", "hi", "gar")
DEFAULT_LANG = "en"

LEVEL_NAMES: dict[str, dict[str, str]] = {
    "green": {"en": "Safe", "hi": "सुरक्षित", "gar": "सुरक्षित"},
    "blue": {"en": "Advisory", "hi": "सूचना", "gar": "सुचना"},
    "yellow": {"en": "Alert", "hi": "चेतावनी", "gar": "चेतवनी"},
    "orange": {"en": "Warning", "hi": "गंभीर चेतावनी", "gar": "गम्भीर चेतवनी"},
    "red": {"en": "Evacuate", "hi": "तुरंत स्थानांतरण", "gar": "तुरंत स्थानांतरण"},
}

HAZARD_NAMES: dict[str, dict[str, str]] = {
    "landslide": {"en": "landslide", "hi": "भूस्खलन", "gar": "भूस्खलन / डंडगिरी"},
    "flash_flood": {"en": "flash flood", "hi": "अचानक बाढ़", "gar": "अचानक बाढ़"},
    "road_block": {"en": "road blockage", "hi": "रास्ता बाधित", "gar": "रास्ता बंद"},
    "debris_flow": {"en": "debris flow", "hi": "मलबे का प्रवाह", "gar": "मलबा प्रवाह"},
    "cloudburst": {"en": "cloudburst", "hi": "अतिवर्षा / क्लाउडबर्स्ट", "gar": "मेला पड़ना"},
    "earthquake": {"en": "seismic activity", "hi": "भूकंपीय गतिविधि", "gar": "भूकंप"},
    "glacial_lake": {"en": "glacial lake outburst risk", "hi": "हिमनदीय झील जोखिम", "gar": "हिमनद झील जोखिम"},
    "water_logging": {"en": "waterlogging", "hi": "जलभराव", "gar": "पानी भरना"},
}

TEMPLATES: dict[str, dict[str, str]] = {
    "alert.subject": {
        "en": "{level} — {hazard} risk in {ward}",
        "hi": "{level} — {ward} में {hazard} का खतरा",
        "gar": "{level} — {ward} मा {hazard} डो खतरा",
    },
    "alert.body_sms": {
        "en": (
            "AapaatSathi {level}: {hazard} risk {score}/100 at {ward}, {district}. "
            "{advice} Help: 1070 / 112."
        ),
        "hi": (
            "आपतसाथी {level}: {ward}, {district} में {hazard} का खतरा {score}/100। "
            "{advice} सहायता: 1070 / 112."
        ),
        "gar": (
            "आपतसाथी {level}: {ward}, {district} मा {hazard} डो खतरा {score}/100 छ। "
            "{advice} सहायता: 1070 / 112."
        ),
    },
    "alert.ivr_script": {
        "en": (
            "This is AapaatSathi emergency warning. Risk level {level} in {ward}, {district}. "
            "{advice} Move to high ground. Do not cross flowing water. "
            "Repeat. This is a warning for {ward}."
        ),
        "hi": (
            "यह आपतसाथी आपात चेतावनी है। {ward}, {district} में स्तर {level}। "
            "{advice} ऊंची जगह पर जाएं। बहते पानी से न गुजरें। "
            "कृपया यह संदेश अपने पड़ोसियों को भी बताएं।"
        ),
        "gar": (
            "यह आपतसाथी डो आपात चेतवनी हो। {ward}, {district} मा स्तर {level} छ। "
            "{advice} उंचाई मा जाव। बहंडो पानी स न जाव। "
            "कृपया आपा डो पड़ोसीयां लै बताव।"
        ),
    },
    "advice.green": {
        "en": "No action needed.",
        "hi": "कार्रवाई की आवश्यकता नहीं।",
        "gar": "कुनै कार्रवाई नइ।",
    },
    "advice.blue": {
        "en": "Stay informed, keep your phone charged.",
        "hi": "सूचित रहें, फोन चार्ज रखें।",
        "gar": "सुचित राखव, फोन चार्ज राखव।",
    },
    "advice.yellow": {
        "en": "Avoid slopes and riverbanks. Pack essentials.",
        "hi": "ढलान और नदी किनारे से बचें। जरूरी सामान तैयार रखें।",
        "gar": "ढलान अ नदी किनारा बचव। जरूरी सामान तैयार राखव।",
    },
    "advice.orange": {
        "en": "Prepare to leave. Move elderly and children uphill now.",
        "hi": "निकलने की तैयारी करें। बुजुर्गों और बच्चों को अभी ऊंचाई पर ले जाएं।",
        "gar": "निकलदा तैयार राखव। बुजुर्ग अ बाला लै अभी उंचाई लै जाव।",
    },
    "advice.red": {
        "en": "EVACUATE NOW. Do not wait. Follow marked shelter routes.",
        "hi": "अभी स्थानांतरित हों। प्रतीक्षा न करें। आश्रय स्थल मार्ग अपनाएं।",
        "gar": "अभी स्थानांतरित हाव। देर न कराव। आश्रय स्थल डो मार्ग लै जाव।",
    },
    "report.received": {
        "en": "Report #{code} received from {ward}. Thank you — this helps your neighbours.",
        "hi": "रिपोर्ट #{code} {ward} से मिली। धन्यवाद — इससे आपके पड़ोसियों की मदद होगी।",
        "gar": "रिपोर्ट #{code} {ward} स मिली। धन्यवाद — इसलां डे पड़ोसीयां डी मदद होला।",
    },
    "report.verified": {
        "en": "Field team confirmed your report #{code}.",
        "hi": "फील्ड टीम ने आपकी रिपोर्ट #{code} की पुष्टि की।",
        "gar": "फील्ड टीम डे तयाली रिपोर्ट #{code} डी पुष्टि करी।",
    },
    "shelter.space": {
        "en": "{name} has {free} free places ({cap} total).",
        "hi": "{name} में {free} स्थान उपलब्ध (कुल {cap})।",
        "gar": "{name} मा {free} थाउ खाली छ (कुल {cap})।",
    },
}

UI_LABELS: dict[str, dict[str, str]] = {
    "app_title": {"en": "AapaatSathi", "hi": "आपतसाथी", "gar": "आपतसाथी"},
    "risk_now": {"en": "Risk right now", "hi": "वर्तमान जोखिम", "gar": "वर्तमान जोखिम"},
    "report_hazard": {"en": "Report a hazard", "hi": "खतरे की सूचना दें", "gar": "खतरा बताव"},
    "nearest_shelter": {"en": "Nearest shelter", "hi": "निकटतम आश्रय", "gar": "नजदीकी आश्रय"},
    "roads": {"en": "Road status", "hi": "सड़क स्थिति", "gar": "रास्ता स्थिति"},
    "help_number": {"en": "Emergency: 112 / 1070", "hi": "आपातकाल: 112 / 1070", "gar": "आपातकाल: 112 / 1070"},
}


def localize(template_key: str, lang: str, **kwargs: Any) -> str:
    """Render a template in `lang`, falling back to English on any miss."""
    entry = TEMPLATES.get(template_key)
    if not entry:
        raise KeyError(f"unknown template {template_key!r}")
    template = entry.get(lang) or entry.get(DEFAULT_LANG) or ""
    try:
        return template.format(**kwargs)
    except KeyError as exc:  # a template gained a variable the caller missed
        raise KeyError(f"template {template_key!r} missing variable {exc}") from exc


def level_name(level: str, lang: str = DEFAULT_LANG) -> str:
    return LEVEL_NAMES.get(level.lower(), {}).get(lang) or level.upper()


def hazard_name(hazard: str, lang: str = DEFAULT_LANG) -> str:
    return HAZARD_NAMES.get(hazard, {}).get(lang) or hazard.replace("_", " ")


def advice_for(level: str, lang: str = DEFAULT_LANG) -> str:
    return localize(f"advice.{level.lower()}", lang)


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    key = lang.strip().lower()[:3]
    if key in SUPPORTED_LANGS:
        return key
    if key.startswith("hin"):
        return "hi"
    if key.startswith("eng"):
        return "en"
    return DEFAULT_LANG


def catalog(lang: str = DEFAULT_LANG) -> dict[str, str]:
    out: dict[str, str] = {}
    out.update({k: v.get(lang, v[DEFAULT_LANG]) for k, v in UI_LABELS.items()})
    out.update({f"level.{k}": v.get(lang, v[DEFAULT_LANG]) for k, v in LEVEL_NAMES.items()})
    out.update({f"hazard.{k}": v.get(lang, v[DEFAULT_LANG]) for k, v in HAZARD_NAMES.items()})
    return out
