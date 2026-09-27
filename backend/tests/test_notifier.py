"""Tests for outbound alert delivery.

The single most important property of this module is *honesty*: with the default
console provider nothing leaves the process, and the system must record that as
``simulated`` rather than ``sent``. A reviewer who cannot trust the delivery
ledger cannot trust the product, so several tests below exist purely to fail if
someone ever makes the convenient change of reporting simulations as sends.
"""

from __future__ import annotations

import time

import pytest

from app.config import settings
from app.models import Channel, Notification, NotificationStatus
from app.services import notifier
from app.services.notifier import (
    ConsoleProvider,
    Dispatcher,
    Msg91Provider,
    SendResult,
    TwilioProvider,
    build_provider,
    compose_alert,
    compose_all_languages,
    ward_lang,
    _ensure_e164,
)
from app.services.i18n import SUPPORTED_LANGS

RED = dict(
    level="red",
    hazard="flash_flood",
    ward_name="Dharali",
    district_name="Uttarkashi",
    score=88.0,
)
YELLOW = dict(
    level="yellow",
    hazard="landslide",
    ward_name="Ranikhot",
    district_name="Pauri Garhwal",
    score=52.0,
)


class RecordingSession:
    """Stands in for an AsyncSession: records rows, flushes, never touches a DB."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    @property
    def notifications(self) -> list[Notification]:
        return [row for row in self.added if isinstance(row, Notification)]


# --------------------------------------------------------------------------- #
# the honesty guarantee
# --------------------------------------------------------------------------- #
async def test_console_provider_reports_simulated_never_sent():
    result = await ConsoleProvider().send_sms("+919876543210", "Evacuate now.")
    assert result.ok is True
    assert result.status == NotificationStatus.SIMULATED.value
    assert result.status != NotificationStatus.SENT.value
    assert result.provider == "console"
    assert result.error is None
    assert result.ref and result.ref.startswith("sim-")


async def test_console_ivr_is_also_marked_simulated():
    result = await ConsoleProvider().send_ivr("+919876543210", "यह आपतसाथी डो आपात चेतवनी हो।")
    assert result.status == NotificationStatus.SIMULATED.value
    assert result.ref.startswith("sim-ivr-")


def test_a_bare_send_result_defaults_to_simulated_not_sent():
    """The dataclass default matters: a forgotten status must not read as delivered."""
    assert SendResult(ok=True).status == NotificationStatus.SIMULATED.value
    assert SendResult(ok=False).status != NotificationStatus.SENT.value


def test_default_configuration_selects_the_console_provider():
    provider = build_provider()
    assert isinstance(provider, ConsoleProvider)
    assert provider.name == "console"


def test_build_provider_falls_back_to_console_when_credentials_are_missing(monkeypatch):
    monkeypatch.setattr(settings, "sms_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "")
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(settings, "twilio_from_number", "")
    assert isinstance(build_provider(), ConsoleProvider)

    monkeypatch.setattr(settings, "sms_provider", "msg91")
    monkeypatch.setattr(settings, "msg91_auth_key", "")
    assert isinstance(build_provider(), ConsoleProvider)

    # half-configured Twilio (key but no sender) must not half-send either
    monkeypatch.setattr(settings, "sms_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACxxxxxxxxxxxxxxxx")
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    assert isinstance(build_provider(), ConsoleProvider)


def test_an_unknown_provider_name_is_console(monkeypatch):
    monkeypatch.setattr(settings, "sms_provider", "carrier-pigeon")
    assert isinstance(build_provider(), ConsoleProvider)


def test_provider_names_match_the_configuration_keywords():
    """``build_provider`` dispatches on these strings, so a rename is a breaking change."""
    assert TwilioProvider.name == "twilio"
    assert Msg91Provider.name == "msg91"
    assert ConsoleProvider.name == "console"


async def test_msg91_refuses_ivr_rather_than_pretending_it_worked():
    provider = Msg91Provider()
    try:
        result = await provider.send_ivr("+919876543210", "voice script")
        assert result.ok is False
        assert result.status == NotificationStatus.FAILED.value
        assert result.error and "IVR" in result.error
        assert result.provider == "msg91"
    finally:
        await provider.close()


async def test_dispatch_records_every_row_as_simulated_for_a_red_alert():
    session = RecordingSession()
    dispatcher = Dispatcher(provider=ConsoleProvider())
    messages = compose_all_languages(**RED)

    tally = await dispatcher.dispatch(
        session,
        alert_id=1,
        recipients=[("+919876543210", "42", "hi")],
        messages=messages,
        channels=[Channel.SMS.value, Channel.IVR.value],
    )
    assert tally == {NotificationStatus.SIMULATED.value: 2}
    rows = session.notifications
    assert len(rows) == 2
    assert {row.status for row in rows} == {NotificationStatus.SIMULATED.value}
    assert "sent" not in str([row.status for row in rows])
    assert all(row.provider == "console" for row in rows)
    assert all(row.sent_at is not None for row in rows)
    assert {row.channel for row in rows} == {"sms", "ivr"}
    assert all(row.lang == "hi" for row in rows)
    assert all(row.body in (messages["hi"]["sms"], messages["hi"]["ivr"]) for row in rows)


async def test_dispatch_is_reachable_via_the_default_singleton():
    """The module-level dispatcher the app uses must be the console by default."""
    assert notifier.dispatcher.provider.name == "console"
    assert (await notifier.dispatcher.stats())["provider"] == "console"


# --------------------------------------------------------------------------- #
# composition
# --------------------------------------------------------------------------- #
def test_compose_all_languages_returns_en_hi_and_gar():
    messages = compose_all_languages(**RED)
    assert list(messages) == list(SUPPORTED_LANGS)
    for lang, body in messages.items():
        assert set(body) >= {"lang", "level_name", "hazard_name", "advice", "subject", "sms", "ivr"}
        assert body["lang"] == lang
        assert body["subject"].strip()
        assert body["sms"].strip()
        assert body["ivr"].strip()


def test_each_language_gets_its_own_copy_and_the_localised_level_name():
    messages = compose_all_languages(**RED)
    subjects = {m["subject"] for m in messages.values()}
    assert len(subjects) == 3, "languages must not be identical strings"
    assert messages["en"]["level_name"] == "Evacuate"
    assert messages["hi"]["level_name"] == "तुरंत स्थानांतरण"
    assert messages["gar"]["level_name"] == "तुरंत स्थानांतरण"
    assert messages["en"]["hazard_name"] == "flash flood"


def test_composed_copy_carries_the_ward_district_rounded_score_and_advice():
    messages = compose_all_languages(**RED)
    sms = messages["en"]["sms"]
    assert "Dharali" in sms and "Uttarkashi" in sms
    assert "88/100" in sms, "score must be rendered as an integer out of 100"
    assert "EVACUATE NOW" in sms
    assert "1070" in sms and "112" in sms, "emergency numbers are part of the contract"
    assert messages["en"]["advice"] in sms


def test_compose_alert_normalises_the_requested_language():
    assert compose_alert(lang="Hindi", **RED)["lang"] == "hi"
    assert compose_alert(lang="gar", **RED)["lang"] == "gar"
    assert compose_alert(lang="kumaoni", **RED)["lang"] == "en"


def test_no_template_variable_is_left_unrendered():
    messages = compose_all_languages(**YELLOW)
    for lang, body in messages.items():
        for field in ("subject", "sms", "ivr"):
            assert "{" not in body[field] and "}" not in body[field], (lang, field)


def test_sms_bodies_stay_inside_a_single_segment_for_most_languages():
    """A 160-char limit is a real constraint on a feature phone."""
    messages = compose_all_languages(**RED)
    assert len(messages["en"]["sms"]) <= 170


# --------------------------------------------------------------------------- #
# dedupe and throttling
# --------------------------------------------------------------------------- #
def test_dedupe_suppresses_inside_the_window_and_allows_after_it():
    dispatcher = Dispatcher(provider=ConsoleProvider())
    assert dispatcher._deduped("1:red:landslide", 90) is False, "first alert must go out"
    assert dispatcher._deduped("1:red:landslide", 90) is True, "duplicate inside the window"
    assert dispatcher._deduped("2:red:landslide", 90) is False, "keys are independent"

    # age the entry past the window instead of sleeping
    dispatcher._recent["1:red:landslide"] = time.monotonic() - 91 * 60
    assert dispatcher._deduped("1:red:landslide", 90) is False
    assert dispatcher._deduped("1:red:landslide", 0) is False, "a zero window never suppresses"


def test_dedupe_window_matches_the_configured_value():
    dispatcher = Dispatcher(provider=ConsoleProvider())
    key = "9:orange:landslide"
    assert dispatcher._deduped(key, settings.dedupe_window_minutes) is False
    window = settings.dedupe_window_minutes * 60
    assert (time.monotonic() - dispatcher._recent[key]) < window
    assert dispatcher._deduped(key, settings.dedupe_window_minutes) is True


async def test_a_suppressed_dispatch_sends_nothing_and_records_nothing():
    session = RecordingSession()
    dispatcher = Dispatcher(provider=ConsoleProvider())
    messages = compose_all_languages(**RED)
    recipients = [("+919876543210", "1", "en"), ("+919876543211", "2", "hi")]

    first = await dispatcher.dispatch(
        session, alert_id=7, recipients=recipients, messages=messages, dedupe_key="ward-7:red:landslide"
    )
    rows_after_first = len(session.notifications)
    assert first == {NotificationStatus.SIMULATED.value: 4}  # 2 phones x (sms + ivr)

    second = await dispatcher.dispatch(
        session, alert_id=7, recipients=recipients, messages=messages, dedupe_key="ward-7:red:landslide"
    )
    assert second == {"suppressed": 4}
    assert len(session.notifications) == rows_after_first


def test_throttle_counts_messages_and_blocks_once_the_rate_is_reached():
    dispatcher = Dispatcher(provider=ConsoleProvider(), max_per_minute=3)
    assert [dispatcher._throttle_ok() for _ in range(4)] == [True, True, True, False]
    assert len(dispatcher._sent_this_minute) == 3

    # simulated ageing: everything is now outside the 60 s window
    dispatcher._sent_this_minute[:] = [t - 61 for t in dispatcher._sent_this_minute]
    assert dispatcher._throttle_ok() is True
    assert len(dispatcher._sent_this_minute) == 1


async def test_throttled_recipients_are_persisted_as_queued():
    session = RecordingSession()
    dispatcher = Dispatcher(provider=ConsoleProvider(), max_per_minute=1)
    messages = compose_all_languages(**RED)
    tally = await dispatcher.dispatch(
        session,
        alert_id=11,
        recipients=[("+919876543210", "5", "en"), ("+919876543211", "6", "en")],
        messages=messages,
        channels=[Channel.SMS.value],
    )
    assert tally == {
        NotificationStatus.SIMULATED.value: 1,
        NotificationStatus.QUEUED.value: 1,
    }
    rows = session.notifications
    assert len(rows) == 2
    queued = [r for r in rows if r.status == NotificationStatus.QUEUED.value]
    assert len(queued) == 1
    assert queued[0].attempts == 0
    assert queued[0].sent_at is None
    assert queued[0].body == messages["en"]["sms"]


async def test_ivr_is_reserved_for_orange_and_red_in_every_language():
    dispatcher = Dispatcher(provider=ConsoleProvider())
    high = compose_all_languages(**RED)
    low = compose_all_languages(**YELLOW)
    for lang in SUPPORTED_LANGS:
        assert Dispatcher._should_call(lang, high[lang]) is True
        assert Dispatcher._should_call(lang, low[lang]) is False

    session = RecordingSession()
    tally = await dispatcher.dispatch(
        session,
        alert_id=12,
        recipients=[("+919876543210", "9", "gar")],
        messages=low,
        channels=[Channel.SMS.value, Channel.IVR.value],
    )
    assert tally == {NotificationStatus.SIMULATED.value: 1}
    assert [r.channel for r in session.notifications] == [Channel.SMS.value]


async def test_recipients_without_a_phone_are_skipped_and_language_falls_back_to_english():
    session = RecordingSession()
    dispatcher = Dispatcher(provider=ConsoleProvider())
    messages = compose_all_languages(**RED)
    tally = await dispatcher.dispatch(
        session,
        alert_id=13,
        recipients=[(None, "1", "en"), ("", "2", "hi"), ("+919876543212", "3", "boapali")],
        messages=messages,
        channels=[Channel.SMS.value],
    )
    assert tally == {NotificationStatus.SIMULATED.value: 1}
    row = session.notifications[0]
    assert row.lang == "en"
    assert row.user_id == 3


# --------------------------------------------------------------------------- #
# phone normalisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+919876543210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("98765-43210", "+919876543210"),
        ("tel:+919876543210", "+919876543210"),
        ("+91 (0) 98765 43210", "+9109876543210"),
    ],
)
def test_ensure_e164_accepts_the_shapes_a_real_forms_sends(raw, expected):
    assert _ensure_e164(raw, "91") == expected


@pytest.mark.parametrize("raw", ["+919876543210", "9876543210", "919876543210", "+91 98765 43210"])
def test_ensure_e164_is_idempotent(raw):
    once = _ensure_e164(raw, "91")
    assert once.startswith("+")
    assert _ensure_e164(once, "91") == once
    assert _ensure_e164(once, "") == once
    assert _ensure_e164(_ensure_e164(once, "91"), "91") == once


def test_ensure_e164_keeps_an_explicit_international_prefix():
    assert _ensure_e164("+14155550123", "91") == "+14155550123"
    assert _ensure_e164("+1 415 555 0123", "91") == "+14155550123"


def test_msg91_route_strips_the_plus_for_a_domestic_sender_id():
    assert _ensure_e164("9876543210", "").lstrip("+") == "9876543210"


# --------------------------------------------------------------------------- #
# language defaulting per ward
# --------------------------------------------------------------------------- #
def test_ward_lang_picks_garhwali_for_the_garhwal_belt():
    class FakeWard:
        def __init__(self, code):
            self.code = code

    assert ward_lang(FakeWard("PKR-RNK")) == "gar"
    assert ward_lang(FakeWard("RPR-PHT")) == "gar"
    assert ward_lang(FakeWard("pkr-rnk")) == "gar"
    assert ward_lang(FakeWard("NNT-BHM")) == "hi"
    assert ward_lang(FakeWard("DEH-MUS")) == "hi"
