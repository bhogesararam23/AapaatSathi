"""Tests for the localisation layer.

A mistranslated evacuation order is worse than no order, so the guarantees here
are strict: no template may be missing a language, no template may render half
filled, and an unknown variable must raise rather than silently ship a message
with `{ward}` in it.
"""

from __future__ import annotations

import string
import unicodedata

import pytest

from app.services.i18n import (
    DEFAULT_LANG,
    HAZARD_NAMES,
    LEVEL_NAMES,
    SUPPORTED_LANGS,
    TEMPLATES,
    UI_LABELS,
    advice_for,
    catalog,
    hazard_name,
    level_name,
    localize,
    normalize_lang,
)

DEVANAGARI = ("\u0900", "\u097f")

# Values good enough to satisfy every placeholder in the catalog.
SAMPLE = {
    "level": "Warning",
    "hazard": "landslide",
    "ward": "Ranikhot-Bhaironghat",
    "district": "Pauri Garhwal",
    "score": 71,
    "advice": "Prepare to leave.",
    "code": "HR-260927-AB12",
    "name": "Ranikhot GSB Intermediate College",
    "free": 120,
    "cap": 520,
}


def is_devanagari(text: str) -> bool:
    return any(DEVANAGARI[0] <= ch <= DEVANAGARI[1] for ch in text)


def fields_of(template: str) -> set[str]:
    """The placeholder names a template consumes."""
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


# --------------------------------------------------------------------------- #
# catalog integrity
# --------------------------------------------------------------------------- #
def test_the_catalog_only_ships_supported_languages():
    for table in (TEMPLATES, LEVEL_NAMES, HAZARD_NAMES, UI_LABELS):
        for key, entry in table.items():
            assert set(entry) == set(SUPPORTED_LANGS), f"{key} is not trilingual: {sorted(entry)}"


def test_every_template_key_renders_in_all_three_languages():
    for key in TEMPLATES:
        for lang in SUPPORTED_LANGS:
            text = localize(key, lang, **SAMPLE)
            assert text.strip(), f"{key}/{lang} rendered empty"
            assert "{" not in text and "}" not in text, f"{key}/{lang} left a raw placeholder"


@pytest.mark.parametrize("lang", SUPPORTED_LANGS)
def test_english_copy_is_ascii_friendly_and_localised_copy_is_not(lang):
    """The gar/hi catalogs must actually be translated, not pasted English."""
    hindi = localize("alert.subject", "hi", **SAMPLE)
    garhwali = localize("alert.subject", "gar", **SAMPLE)
    english = localize("alert.subject", "en", **SAMPLE)
    assert not is_devanagari(english)
    assert is_devanagari(hindi)
    assert is_devanagari(garhwali)
    assert hindi != garhwali  # Garhwali is not quietly aliased to Hindi
    assert lang in SUPPORTED_LANGS


def test_devanagari_text_is_nfc_normalised_for_sms():
    """Combining marks survive a GSM 7-bit / Unicode SMS round trip only when NFC."""
    for lang in ("hi", "gar"):
        for key, entry in TEMPLATES.items():
            text = entry[lang]
            assert text == unicodedata.normalize("NFC", text), f"{key}/{lang} is not NFC"


# --------------------------------------------------------------------------- #
# fail-loudly contract
# --------------------------------------------------------------------------- #
def test_a_missing_variable_raises_instead_of_emitting_a_half_filled_alert():
    with pytest.raises(KeyError) as exc:
        localize("alert.subject", "en", level="Evacuate")  # no hazard, no ward
    assert "alert.subject" in str(exc.value)
    assert "hazard" in str(exc.value)


def test_a_missing_variable_raises_in_every_language():
    for lang in SUPPORTED_LANGS:
        with pytest.raises(KeyError):
            localize("alert.body_sms", lang, level="x", hazard="y")


def test_an_unknown_template_key_raises():
    with pytest.raises(KeyError):
        localize("alert.nonexistent", "en")


def test_unknown_language_falls_back_to_english_but_unknown_key_still_raises():
    assert localize("alert.subject", "boapali", **SAMPLE) == localize("alert.subject", "en", **SAMPLE)
    with pytest.raises(KeyError):
        localize("alert.subject", "boapali")


def test_each_template_declares_only_variables_the_sample_provides():
    """Guards against a template gaining a placeholder no caller knows about."""
    for key, entry in TEMPLATES.items():
        for lang, template in entry.items():
            missing = fields_of(template) - set(SAMPLE)
            assert not missing, f"{key}/{lang} needs undeclared {sorted(missing)}"


# --------------------------------------------------------------------------- #
# normalize_lang
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("hin", "hi"),
        ("Hindi", "hi"),
        ("hi", "hi"),
        ("HI", "hi"),
        (" hin-IN ", "hi"),
        ("eng", "en"),
        ("English", "en"),
        ("en", "en"),
        ("gar", "gar"),
        ("GARHWALI", "gar"),
        (None, "en"),
        ("", "en"),
        ("   ", "en"),
        ("klingon", "en"),
        ("zz", "en"),
    ],
)
def test_normalize_lang_maps_to_a_supported_code(raw, expected):
    assert normalize_lang(raw) == expected


def test_normalize_lang_output_is_always_renderable():
    for raw in ("hin", "gar", "en", "und", None, "", "x" * 40):
        lang = normalize_lang(raw)
        assert lang in SUPPORTED_LANGS
        assert localize("alert.subject", lang, **SAMPLE)


# --------------------------------------------------------------------------- #
# names and advice
# --------------------------------------------------------------------------- #
def test_advice_for_red_in_hindi_is_non_empty_hindi():
    advice = advice_for("red", "hi")
    assert advice
    assert is_devanagari(advice)
    assert advice == TEMPLATES["advice.red"]["hi"]
    assert advice != advice_for("red", "en")


@pytest.mark.parametrize("level", ["green", "blue", "yellow", "orange", "red"])
def test_every_level_has_advice_in_every_language(level):
    texts = {lang: advice_for(level, lang) for lang in SUPPORTED_LANGS}
    assert all(t.strip() for t in texts.values())
    assert len(set(texts.values())) >= 2


def test_advice_sharpens_with_the_level():
    """The red instruction must be more urgent than the green one, in English."""
    assert advice_for("green", "en").lower() == "no action needed."
    assert "evacuate" in advice_for("red", "en").lower()
    assert len(advice_for("red", "en")) > len(advice_for("blue", "en"))


def test_level_and_hazard_names_localize_and_degrade_gracefully():
    assert level_name("red", "en") == "Evacuate"
    assert level_name("RED", "hi") == LEVEL_NAMES["red"]["hi"]
    assert level_name("chartreuse", "en") == "CHARTREUSE"
    # An unsupported language has no translation to offer, so the ASCII level
    # token is returned rather than a blank or a wrong-language guess.
    assert level_name("red", "boapali") == "RED"
    assert hazard_name("flash_flood", "hi") == HAZARD_NAMES["flash_flood"]["hi"]
    assert hazard_name("sinkhole", "en") == "sinkhole"  # underscores become spaces
    assert hazard_name("volcanic_ash", "en") == "volcanic ash"


def test_garhwali_level_names_are_distinct_from_hindi_where_they_should_be():
    assert LEVEL_NAMES["orange"]["gar"] != LEVEL_NAMES["orange"]["hi"]
    assert HAZARD_NAMES["landslide"]["gar"] != HAZARD_NAMES["landslide"]["hi"]


def test_catalog_is_a_flat_language_complete_lookup():
    for lang in SUPPORTED_LANGS:
        table = catalog(lang)
        assert table
        assert all(v.strip() for v in table.values())
        assert any(key.startswith("level.") for key in table)
        assert any(key.startswith("hazard.") for key in table)
        assert table["app_title"] == "आपतसाथी" if lang != "en" else table["app_title"] == "AapaatSathi"


def test_catalog_falls_back_to_english_for_an_unknown_language():
    assert catalog("boapali") == catalog(DEFAULT_LANG)


def test_report_templates_read_as_a_confirmation_to_the_reporter():
    text = localize("report.received", "hi", code="HR-1", ward="Ranikhot")
    assert "HR-1" in text and "Ranikhot" in text and is_devanagari(text)
    verified = localize("report.verified", "gar", code="HR-1")
    assert "HR-1" in verified and is_devanagari(verified)
