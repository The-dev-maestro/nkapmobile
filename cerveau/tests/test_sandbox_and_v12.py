from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.contracts import (
    ActionMessage,
    ActionPayload,
    ActionTarget,
    BarItem,
    ChoiceItem,
    FlowStep,
    ScreenContext,
)
from app.core.validators import validate_action_stream
from app.main import app
from app.sandbox.gsm7 import gsm7_length, is_gsm7, to_gsm7
from app.sandbox.language import TRANSLATIONS_DIR, translate_ui
from app.sandbox.ussd_flow import SESSIONS, handle_channel_turn

client = TestClient(app)


def _placeholders(text: str) -> list[str]:
    return sorted(set(re.findall(r"\{[a-z_]+\}", text)))


def test_translations_complete_and_placeholders_intact():
    en = json.loads((TRANSLATIONS_DIR / "en.json").read_text(encoding="utf-8"))
    for lang in ("ewo", "dua"):
        tr = json.loads((TRANSLATIONS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        assert set(tr.keys()) == set(en.keys()), f"Clés manquantes ou en trop dans {lang}.json"
        for key, en_val in en.items():
            val = tr[key]
            assert isinstance(val, str) and val.strip(), f"Clé vide {lang}.{key}"
            assert _placeholders(val) == _placeholders(en_val), (
                f"Placeholders cassés sur {lang}.{key}: {val!r} vs {en_val!r}"
            )
            if key.startswith("nav."):
                assert len(val) <= 12, f"{lang}.{key} dépasse 12 car.: {val!r}"
            if key.startswith("tx.status."):
                assert len(val) <= 16, f"{lang}.{key} dépasse 16 car.: {val!r}"
            if key.startswith("home.action_"):
                assert len(val) <= 28, f"{lang}.{key} dépasse 28 car.: {val!r}"


def test_sandbox_ui_translation_honest_and_respects_constraints():
    payload = {
        "trace_id": "tr-ui-1",
        "channel": "web",
        "type": "ui_translation",
        "language": "ewo",
        "source_language": "fr",
        "screen": "home",
        "strings": {
            "nav.home": {"text": "Accueil", "max_chars": 12},
            "home.balance_label": {"text": "Solde disponible", "max_chars": None},
            "error.INSUFFICIENT_FUNDS": {
                "text": "Solde insuffisant : il vous manque {missing}.",
                "max_chars": None,
            },
        },
    }
    resp = client.post("/sandbox", json=payload, headers={"X-Trace-Id": "tr-ui-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "ewo"
    assert len(body["strings"]["nav.home"]) <= 12
    assert "{missing}" in body["strings"]["error.INSUFFICIENT_FUNDS"]
    assert body["strings"]["home.balance_label"] == "Itan ineu"

    # Langue non supportée -> déclaration honnête "fr"
    unsupported = dict(payload, language="fub")
    resp2 = client.post("/sandbox", json=unsupported)
    assert resp2.status_code == 200
    assert resp2.json()["language"] == "fr"


def test_gsm7_transliteration_strips_african_non_gsm7_chars():
    sample = "Nděn ɔ́g bɔ́l, ɛlɛ́ɛ́ nem tɛlɛfɔ́n — ɓasaá ’ 15 000 FCFA"
    out = to_gsm7(sample)
    assert is_gsm7(out)
    assert "15 000 FCFA" in out
    assert gsm7_length(out) <= 182


def _mock_bank():
    bank = MagicMock()
    bank.balance.return_value = (True, 200, {"balance": 120000})
    bank.fees.return_value = (True, 200, {"fee": 150, "total": 25150})
    bank.history.return_value = (
        True,
        200,
        {"transactions": [{"type": "transfer", "to_name": "Paul", "amount": 5000, "status": "confirmed"}]},
    )
    bank.beneficiaries.return_value = (
        True,
        200,
        {"beneficiaries": [{"name": "Paul Mbarga", "phone": "237699000002"}]},
    )
    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-001", "amount": 25000, "fee": 150, "total": 25150, "to": "237699000002", "status": "pending"},
    )
    bank.confirm.return_value = (
        True,
        200,
        {"id": "TRX-001", "amount": 25000, "to": "237699000002", "status": "confirmed"},
    )
    bank.cancel.return_value = (True, 200, {"id": "TRX-001", "status": "cancelled"})
    return bank


def test_ussd_all_core_scenarios_and_gsm7():
    SESSIONS.clear()
    bank = _mock_bank()

    # 1. Solde en ewondo sans dire "solde"
    r1 = handle_channel_turn(
        {"session_id": "s1", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "itan ineu"}},
        trace_id="t1",
        bank_client=bank,
    )
    assert r1["interpretation"]["intent"] == "BALANCE_INQUIRY"
    assert r1["interpretation"]["language"] == "ewo"
    assert "120 000 FCFA" in r1["response"]["text"]
    assert is_gsm7(r1["response"]["text"]) and gsm7_length(r1["response"]["text"]) <= 182

    # 2. Demande de frais (25 000 -> 150)
    r_fee = handle_channel_turn(
        {"session_id": "s_fee", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "mbug 25000"}},
        trace_id="t2",
        bank_client=bank,
    )
    assert r_fee["interpretation"]["intent"] == "FEE_INQUIRY"
    assert "150 FCFA" in r_fee["response"]["text"]
    bank.fees.assert_called_with("transfer", 25000)

    # 3. Transfert -> Correction -> Changement de langue -> Confirmation (tours séparés!)
    r_tr = handle_channel_turn(
        {"session_id": "s_tr", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "lomo 25000 a Paul"}},
        trace_id="t3",
        bank_client=bank,
    )
    assert r_tr["interpretation"]["intent"] == "TRANSFER"
    assert r_tr["transaction"]["status"] == "pending"
    assert r_tr["response"]["end_session"] is False

    # Correction avant confirmation (annule TRX-001 et recrée TRX-002 avec frais recalculés)
    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-002", "amount": 5000, "fee": 50, "total": 5050, "to": "237699000002", "status": "pending"},
    )
    r_cor = handle_channel_turn(
        {"session_id": "s_tr", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "modifier 5000"}},
        trace_id="t4",
        bank_client=bank,
    )
    assert r_cor["interpretation"]["intent"] == "CORRECTION"
    assert r_cor["transaction"]["id"] == "TRX-002"
    assert "50 FCFA" in r_cor["response"]["text"]
    bank.cancel.assert_called_with("TRX-001")

    # Changement de langue en plein récapitulatif sans perdre TRX-002
    r_sw = handle_channel_turn(
        {"session_id": "s_tr", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "passer en duala"}},
        trace_id="t5",
        bank_client=bank,
    )
    assert r_sw["interpretation"]["intent"] == "LANGUAGE_SWITCH"
    assert r_sw["interpretation"]["language"] == "dua"
    assert r_sw["transaction"]["id"] == "TRX-002"

    # Confirmation au tour suivant en Duala
    bank.confirm.return_value = (
        True,
        200,
        {"id": "TRX-002", "amount": 5000, "to": "237699000002", "status": "confirmed"},
    )
    r_ok = handle_channel_turn(
        {"session_id": "s_tr", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "1"}},
        trace_id="t6",
        bank_client=bank,
    )
    assert r_ok["interpretation"]["intent"] == "CONFIRM"
    assert r_ok["interpretation"]["language"] == "dua"
    assert r_ok["transaction"]["status"] == "confirmed"
    assert r_ok["response"]["end_session"] is True


def test_ussd_ambiguous_beneficiary_insufficient_funds_and_terminology():
    SESSIONS.clear()
    bank = _mock_bank()
    bank.beneficiaries.return_value = (
        True,
        200,
        {
            "beneficiaries": [
                {"name": "Paul Mbarga", "phone": "237699000002"},
                {"name": "Paul Nkodo", "phone": "237699000003"},
            ]
        },
    )
    r_amb = handle_channel_turn(
        {"session_id": "s_amb", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "lomo 5000 a Paul"}},
        trace_id="t7",
        bank_client=bank,
    )
    assert r_amb["interpretation"]["intent"] == "CLARIFICATION_NEEDED"
    assert bank.create_transaction.call_count == 0

    # Solde insuffisant -> jamais le code brut
    bank.beneficiaries.return_value = (True, 200, {"beneficiaries": [{"name": "Amina", "phone": "237699000004"}]})
    bank.create_transaction.return_value = (False, 422, {"error": "INSUFFICIENT_FUNDS"})
    r_ins = handle_channel_turn(
        {"session_id": "s_ins", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "lomo 400000 a Amina"}},
        trace_id="t8",
        bank_client=bank,
    )
    assert "INSUFFICIENT_FUNDS" not in r_ins["response"]["text"]
    assert r_ins["interpretation"]["language"] == "ewo"

    # Terminologie financière
    r_term = handle_channel_turn(
        {"session_id": "s_term", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "c'est quoi plafond ?"}},
        trace_id="t9",
        bank_client=bank,
    )
    assert r_term["interpretation"]["intent"] == "TERM_EXPLANATION"
    assert "500 000 FCFA" in r_term["response"]["text"]


def test_v12_visual_actions_and_amount_guard():
    scene = ScreenContext.model_validate(
        {
            "type": "screen_context",
            "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Web"},
            "channel": "web",
            "screen_hint": "review",
            "nodes": [
                {"node_id": "n_01", "tag": "p", "text": "25 000 FCFA", "bounds": [10, 10, 120, 30], "tone": "light"},
                {"node_id": "n_02", "tag": "p", "text": "150 FCFA", "bounds": [10, 40, 120, 60], "tone": "light"},
                {"node_id": "n_03", "tag": "button", "text": "Confirmer", "clickable": True, "bounds": [10, 80, 140, 115], "tone": "dark"},
            ],
        }
    )

    valid_stream = [
        ActionMessage(
            seq=1,
            action=ActionPayload(
                t="notebook",
                id="nb_flow",
                mode="flow",
                title="Trajet du transfert",
                flow_steps=[
                    FlowStep(label="Montant", value="25 000 FCFA", tone="yellow"),
                    FlowStep(label="Frais", value="150 FCFA", tone="green"),
                ],
            ),
        ),
        ActionMessage(
            seq=2,
            action=ActionPayload(t="callout", id="co_1", target=ActionTarget(node_id="n_01"), label="25 000 FCFA", color="yellow"),
        ),
        ActionMessage(
            seq=3,
            action=ActionPayload(t="num", id="num_1", target=ActionTarget(node_id="n_03"), step=1, label="Confirmer", color="red"),
        ),
    ]
    assert len(validate_action_stream(valid_stream, scene)) == 3

    # Montant halluciné dans flow_steps -> rejeté par AmountGuard !
    bad_flow = [
        ActionMessage(
            seq=1,
            action=ActionPayload(
                t="notebook",
                id="nb_bad",
                mode="flow",
                title="Trajet",
                flow_steps=[FlowStep(label="Montant", value="99 999 FCFA")],
            ),
        )
    ]
    with pytest.raises(ValueError, match="Étape flow non autorisée"):
        validate_action_stream(bad_flow, scene)

    # Montant halluciné dans bars / choices -> rejeté
    bad_bars = [
        ActionMessage(
            seq=1,
            action=ActionPayload(
                t="notebook",
                id="nb_bar",
                mode="bars",
                title="Comparaison",
                bars=[BarItem(label="Envoi", value=88888, amount_text="88 888 FCFA")],
            ),
        )
    ]
    with pytest.raises(ValueError, match="Barre comparative non autorisée"):
        validate_action_stream(bad_bars, scene)

    bad_choice = [
        ActionMessage(
            seq=1,
            action=ActionPayload(
                t="notebook",
                id="nb_ch",
                mode="choices",
                title="Choisir",
                choices=[ChoiceItem(id="c1", key="1", label="Envoyer 77 777 FCFA", value="77777")],
            ),
        )
    ]
    with pytest.raises(ValueError, match="Choix non autorisé"):
        validate_action_stream(bad_choice, scene)
