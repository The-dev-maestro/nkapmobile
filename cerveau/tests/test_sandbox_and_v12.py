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
    assert body["strings"]["home.balance_label"] == "Itáŋ inə́ á ŋkwáp"

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


def test_http_answer_explains_financial_concepts_and_distinguishes_balances(monkeypatch):
    # 1. "c'est quoi une micro finance" sur écran USSD quasi vide -> explication pédagogique immédiate (0 appel LLM, PAS Hors contexte)
    llm_calls = []

    def fail_if_called(*args, **kwargs):
        llm_calls.append(kwargs)
        raise AssertionError("Le glossaire pédagogique instantané ne doit pas appeler Ollama")

    monkeypatch.setattr("app.llm.requests.post", fail_if_called)

    ussd_empty_ctx = {
        "type": "screen_context",
        "channel": "ussd",
        "page": {"url": "https://safinum.cm/sandbox/ussd", "title": "Simulateur USSD"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_01", "tag": "div", "text": "Composez *123#", "clickable": False, "bounds": [300, 200, 500, 230], "tone": "dark"},
        ],
    }
    for concept_q, expected_word in (
        ("c'est quoi une micro finance", "microfinance"),
        ("Explique moi c'est quoi un plafond ?", "plafond"),
        ("Que veut dire bénéficiaire ?", "bénéficiaire"),
        ("C'est quoi le mobile money ?", "porte-monnaie"),
        ("C'est quoi l'USSD ?", "internet"),
        ("C'est quoi un taux d'intérêt ?", "pourcentage"),
    ):
        resp = client.post("/answer", json={"transcript": concept_q, "lang_hint": "fr", "context": ussd_empty_ctx})
        assert resp.status_code == 200, f"Échec sur {concept_q}: {resp.text}"
        body = resp.json()
        assert body["meta"]["intent"] == "TERM_EXPLANATION"
        spoken = " ".join(a["action"].get("text", "") for a in body["actions"] if a["action"]["t"] == "speak").lower()
        assert "incapable" not in spoken and "hors contexte" not in spoken
        assert expected_word in spoken
        # Définitions simples -> voix + sous-titres légers sans encombrer l'écran d'un tableau inutile
        assert all(a["action"].get("title") != "Hors contexte" for a in body["actions"] if a["action"]["t"] == "notebook")
    assert len(llm_calls) == 0

    # 2. Concept financier non listé dans le glossaire ("c'est quoi une caution bancaire ?") -> passe au LLM conceptuel (jamais bloqué Hors contexte)
    class _FakeConceptResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": json.dumps(
                    {
                        "spoken": "Une caution bancaire est un engagement par lequel la banque garantit un paiement si tu ne peux pas payer.",
                        "title": "La caution bancaire",
                        "rows": ["• Garantie donnée par la banque", "→ Vérifie les frais avant de signer"],
                        "targets": [],
                    },
                    ensure_ascii=False,
                )
            }

    concept_llm_calls = []

    def fake_concept_llm(url, json=None, timeout=None, **kwargs):
        concept_llm_calls.append(json)
        return _FakeConceptResp()

    monkeypatch.setattr("app.llm.requests.post", fake_concept_llm)
    resp_inf = client.post(
        "/answer",
        json={"transcript": "C'est quoi une caution bancaire ?", "lang_hint": "fr", "context": ussd_empty_ctx},
    )
    assert resp_inf.status_code == 200
    assert len(concept_llm_calls) == 1
    body_inf = resp_inf.json()
    assert body_inf["meta"]["intent"] == "TERM_EXPLANATION"
    spoken_inf = " ".join(a["action"].get("text", "") for a in body_inf["actions"] if a["action"]["t"] == "speak").lower()
    assert "caution" in spoken_inf and "incapable" not in spoken_inf

    # 3. Distinction stricte "Solde disponible" (120 000 FCFA) vs "Solde après opération" (94 850 FCFA)
    # Même si le petit LLM 1.5B confond et cite 94 850 FCFA, le garde sémantique corrige vers 120 000 FCFA !
    class _FakeConfusedBalanceResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": json.dumps(
                    {
                        "spoken": "Ton solde après l'opération est de 94 850 FCFA.",
                        "title": "Solde",
                        "targets": ["94 850 FCFA"],
                    },
                    ensure_ascii=False,
                )
            }

    monkeypatch.setattr("app.llm.requests.post", lambda *a, **kw: _FakeConfusedBalanceResp())
    dual_bal_ctx = {
        "type": "screen_context",
        "channel": "web",
        "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Web Banking"},
        "screen_hint": "review",
        "nodes": [
            {"node_id": "n_hdr", "tag": "div", "text": "SAFINUM WEB BANKING · COMPTE 690 00 00 01", "clickable": False, "bounds": [360, 110, 680, 126], "tone": "light"},
            {"node_id": "n_bal_lbl", "tag": "div", "text": "Solde disponible", "clickable": False, "bounds": [360, 130, 490, 146], "tone": "light"},
            {"node_id": "n_balance", "tag": "div", "text": "120 000 FCFA", "clickable": False, "bounds": [360, 150, 560, 186], "tone": "light"},
            {"node_id": "n_amt_lbl", "tag": "span", "text": "Montant à envoyer", "clickable": False, "bounds": [360, 260, 500, 280], "tone": "light"},
            {"node_id": "n_amount", "tag": "strong", "text": "25 000 FCFA", "clickable": False, "bounds": [780, 260, 920, 280], "tone": "light"},
            {"node_id": "n_after_lbl", "tag": "span", "text": "Solde après opération", "clickable": False, "bounds": [360, 340, 520, 360], "tone": "light"},
            {"node_id": "n_after", "tag": "strong", "text": "94 850 FCFA", "clickable": False, "bounds": [780, 340, 920, 360], "tone": "light"},
        ],
    }
    resp_bal = client.post(
        "/answer",
        json={"transcript": "Quel est mon solde ?", "lang_hint": "fr", "context": dual_bal_ctx},
    )
    assert resp_bal.status_code == 200
    acts_bal = resp_bal.json()["actions"]
    spoken_bal = " ".join(a["action"].get("text", "") for a in acts_bal if a["action"]["t"] == "speak")
    assert "120 000 FCFA" in spoken_bal
    # Cible uniquement n_balance (PAS n_after!)
    visual_targets = [
        a["action"]["target"]["node_id"]
        for a in acts_bal
        if a["action"]["t"] in {"circle", "box", "frame", "underline", "callout"} and a["action"].get("target")
    ]
    assert visual_targets == ["n_balance"]

    # 4. USSD /sandbox reconnait aussi "c'est quoi une microfinance"
    SESSIONS.clear()
    bank = _mock_bank()
    r_mf = handle_channel_turn(
        {"session_id": "s_mf", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "c'est quoi une microfinance ?"}},
        trace_id="t_mf",
        bank_client=bank,
    )
    assert r_mf["interpretation"]["intent"] == "TERM_EXPLANATION"
    assert "Microfinance" in r_mf["response"]["text"]
    assert is_gsm7(r_mf["response"]["text"]) and gsm7_length(r_mf["response"]["text"]) <= 182


def test_open_financial_advice_bypasses_canned_glossary_and_recovers_truncated_json(monkeypatch):
    from app.core.m2_service import M2Service
    from app.llm import LLMAdapter

    # 1. Récupération propre d'un JSON tronqué avant l'accolade fermante `}`
    truncated = (
        '{"spoken":"Une caution bancaire est une garantie donnée par ta banque pour sécuriser un engagement.",'
        '"title":"La caution bancaire","rows":["• Garantie officielle de la banque","• Rassure le propriétaire ou le prête'
    )
    parsed = LLMAdapter.parse_model_json(truncated)
    assert "caution bancaire" in parsed["spoken"].lower()
    assert parsed["title"] == "La caution bancaire"
    assert parsed["rows"] == ["• Garantie officielle de la banque"]

    # 2. Conjugaison tutoiement sans "toi ne remboursez"
    fixed_tu = M2Service._enforce_tutoiement("Tu dois payer si vous ne remboursez pas et vous utilisez votre compte.")
    assert "toi ne" not in fixed_tu.lower()
    assert "si tu ne rembourses pas" in fixed_tu.lower()
    assert "tu utilises ton compte" in fixed_tu.lower()

    # 3. "C'est quoi le moyen le plus simple pour épargner ?" NE DOIT PAS déclencher la fiche préfaite "C'est quoi l'épargne ?"
    #    ET "je veux créer un compte mobile money" doit passer au vrai LLM conseiller sans encadrer un titre au hasard !
    advisor_calls = []

    class _FakeAdvisorResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    def fake_advisor(url, json=None, timeout=None, **kwargs):
        prompt = (json or {}).get("prompt", "")
        advisor_calls.append(prompt)
        if "epargner" in prompt.lower() or "épargner" in prompt.lower():
            return _FakeAdvisorResp(
                {
                    "spoken": "Le moyen le plus simple pour épargner est de mettre de côté une petite part dès que tu reçois un revenu, sur un compte séparé.",
                    "title": "Épargner simplement",
                    "rows": ["• Mets de côté dès que tu es payé", "• Sépare ton épargne de tes dépenses du jour", "→ Commence petit mais régulièrement"],
                }
            )
        return _FakeAdvisorResp(
            {
                "spoken": "Pour créer un compte Mobile Money, rends-toi chez un agent agréé ou en agence avec ta carte d'identité et ta carte SIM enregistrée à ton nom.",
                "title": "Créer un compte Mobile Money",
                "rows": ["• Apporte ta pièce d'identité valide", "• Utilise une carte SIM à ton nom", "→ Choisis un code PIN secret sur place"],
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_advisor)
    demo_ctx = {
        "type": "screen_context",
        "channel": "web",
        "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Web Banking"},
        "screen_hint": "review",
        "nodes": [
            {"node_id": "n_00", "tag": "div", "text": "SAFINUM WEB BANKING · COMPTE 690 00 00 01", "clickable": False, "bounds": [360, 110, 680, 126], "tone": "light"},
            {"node_id": "n_bal_lbl", "tag": "div", "text": "Solde disponible", "clickable": False, "bounds": [360, 130, 490, 146], "tone": "light"},
            {"node_id": "n_balance", "tag": "div", "text": "120 000 FCFA", "clickable": False, "bounds": [360, 150, 560, 186], "tone": "light"},
        ],
    }

    r_save = client.post(
        "/answer",
        json={"transcript": "C'est quoi le moyen le plus simple pour épargner?", "lang_hint": "fr", "context": demo_ctx},
    )
    assert r_save.status_code == 200
    acts_save = r_save.json()["actions"]
    nb_save = next(a["action"] for a in acts_save if a["action"]["t"] == "notebook")
    assert nb_save["title"] == "Épargner simplement"
    assert not any(a["action"]["t"] in {"box", "circle", "frame"} for a in acts_save)

    r_momo = client.post(
        "/answer",
        json={"transcript": "je veux créer un compte mobile money", "lang_hint": "fr", "context": demo_ctx},
    )
    assert r_momo.status_code == 200
    acts_momo = r_momo.json()["actions"]
    spoken_momo = " ".join(a["action"].get("text", "") for a in acts_momo if a["action"]["t"] == "speak").lower()
    assert "agent" in spoken_momo or "identité" in spoken_momo
    # Aucun encadrement parasite sur n_00 (SAFINUM WEB BANKING) !
    assert not any(a["action"]["t"] in {"box", "circle", "frame"} for a in acts_momo)
    assert len(advisor_calls) == 2


def test_judicious_v12_visual_tools_and_sandbox_scenario_hardening(monkeypatch):
    from app.sandbox.language import detect_language_switch, detect_term_question

    # 1. Blindages SAFINUM #8, #10 et Duálá
    assert detect_language_switch("en duala") == "dua"
    assert detect_language_switch("en ewondo") == "ewo"
    assert detect_term_question("mbug e ne dze ?") == "fee"
    assert detect_term_question("mususedi e ne dze ?") == "fee"
    assert detect_term_question("nkuk e ne dze ?") == "limit"
    dua = json.loads((TRANSLATIONS_DIR / "dua.json").read_text(encoding="utf-8"))
    assert dua["shell.greeting"] == "Idiba bwam {name}"
    assert dua["review.fee"] == "Mususɛdi"
    assert dua["history.title"] == "Miaŋgo"
    assert dua["common.cancel"] == "Sumua"
    assert dua["common.continue"] == "Wa la ne"
    assert dua["receipt.reference"] == "Epasi"
    assert dua["review.total"] == "Musɔŋgi mu londi"

    # 2. Correction via /update en place (garde la même référence TRX sans annulation parasite)
    SESSIONS.clear()
    bank = _mock_bank()
    bank.update.return_value = (
        True,
        200,
        {"id": "TRX-001", "amount": 10000, "fee": 150, "total": 10150, "status": "pending"},
    )
    r1 = handle_channel_turn(
        {"session_id": "s_upd", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "lomo 5000 a Paul"}},
        trace_id="t_u1",
        bank_client=bank,
    )
    assert r1["transaction"]["id"] == "TRX-001"
    # Régression USSD : GET /beneficiaries?q=<nom> ne doit JAMAIS recevoir le phone de l'expéditeur !
    bank.beneficiaries.assert_called_with("Paul")
    r2 = handle_channel_turn(
        {"session_id": "s_upd", "channel": "ussd", "phone": "237690000001", "language": "ewo", "input": {"text": "modifier 10000"}},
        trace_id="t_u2",
        bank_client=bank,
    )
    assert r2["interpretation"]["intent"] == "CORRECTION"
    assert r2["transaction"]["id"] == "TRX-001"
    assert "150 FCFA" in r2["response"]["text"]
    bank.update.assert_called_with("TRX-001", {"amount": 10000})

    # Régression USSD menu numéroté : "2" (Transfert) ne doit JAMAIS devenir 2 FCFA, et "3" (Modifier) ne doit JAMAIS devenir 3 FCFA !
    SESSIONS.clear()
    m1 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": ""}}, bank_client=bank)
    assert "Transfert" in m1["response"]["text"]
    m2 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "2"}}, bank_client=bank)
    assert "beneficiaire" in m2["response"]["text"].lower()
    m3 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "Paul"}}, bank_client=bank)
    assert "montant" in m3["response"]["text"].lower()
    assert "2 fcfa" not in m3["response"]["text"].lower()
    m4 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "5000"}}, bank_client=bank)
    assert "5 000" in m4["response"]["text"] and "Modifier montant" in m4["response"]["text"] and "Modifier destinataire" in m4["response"]["text"]
    m5 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "3"}}, bank_client=bank)
    assert "nouveau montant" in m5["response"]["text"].lower()
    assert "3 fcfa" not in m5["response"]["text"].lower()
    m6 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "10000"}}, bank_client=bank)
    assert "10 000" in m6["response"]["text"]
    # Choix 4 : Modifier destinataire
    m7 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "4"}}, bank_client=bank)
    assert "destinataire" in m7["response"]["text"].lower()
    bank.beneficiaries.return_value = (True, 200, {"beneficiaries": [{"name": "Brenda Ndi", "phone": "237699000099"}]})
    m8 = handle_channel_turn({"session_id": "s_num", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "Brenda"}}, bank_client=bank)
    assert "Brenda Ndi" in m8["response"]["text"] and "10 000" in m8["response"]["text"]

    # Menu "3" (Frais) doit demander le montant et JAMAIS calculer les frais pour 3 FCFA !
    SESSIONS.clear()
    f1 = handle_channel_turn({"session_id": "s_fee", "channel": "ussd", "phone": "237690000001", "language": "fr", "input": {"text": "3"}}, bank_client=bank)
    assert "montant" in f1["response"]["text"].lower()
    assert "3 fcfa" not in f1["response"]["text"].lower()

    # 3. Choix judicieux v1.2 côté cerveau : table (dépôt/retrait), highlight (frais), flow + callout (solde après), bars (comparaison)
    review_ctx = {
        "type": "screen_context",
        "channel": "web",
        "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Web"},
        "screen_hint": "review",
        "nodes": [
            {"node_id": "n_bal_lbl", "tag": "div", "text": "Solde disponible", "clickable": False, "bounds": [360, 120, 490, 138], "tone": "light"},
            {"node_id": "n_balance", "tag": "div", "text": "120 000 FCFA", "clickable": False, "bounds": [360, 144, 560, 180], "tone": "light"},
            {"node_id": "n_amt_lbl", "tag": "span", "text": "Montant à envoyer", "clickable": False, "bounds": [360, 220, 500, 240], "tone": "light"},
            {"node_id": "n_amount", "tag": "strong", "text": "25 000 FCFA", "clickable": False, "bounds": [780, 220, 900, 240], "tone": "light"},
            {"node_id": "n_fee_lbl", "tag": "span", "text": "Frais de transfert", "clickable": False, "bounds": [360, 260, 500, 280], "tone": "light"},
            {"node_id": "n_fee", "tag": "strong", "text": "150 FCFA", "clickable": False, "bounds": [800, 260, 900, 280], "tone": "light"},
            {"node_id": "n_after_lbl", "tag": "span", "text": "Solde après opération", "clickable": False, "bounds": [360, 300, 520, 320], "tone": "light"},
            {"node_id": "n_after", "tag": "strong", "text": "94 850 FCFA", "clickable": False, "bounds": [780, 300, 900, 320], "tone": "light"},
        ],
    }

    # Table sur concept comparatif dépôt/retrait
    r_tbl = client.post("/answer", json={"transcript": "C'est quoi un dépôt ?", "lang_hint": "fr", "context": review_ctx})
    assert r_tbl.status_code == 200
    nb_tbl = next(a["action"] for a in r_tbl.json()["actions"] if a["action"]["t"] == "notebook")
    assert nb_tbl["mode"] == "table" and len(nb_tbl["columns"]) == 2

    # Highlight sur concept frais ancré à l'écran
    r_hl = client.post("/answer", json={"transcript": "C'est quoi les frais ?", "lang_hint": "fr", "context": review_ctx})
    assert r_hl.status_code == 200
    assert any(a["action"]["t"] == "highlight" and a["action"]["target"]["node_id"] == "n_fee" for a in r_hl.json()["actions"])

    # Flow + callout sur "Combien il me restera après l'opération ?"
    class _FakeFlowResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeFlowResp(
            {
                "spoken": "Ton solde après opération sera de 94 850 FCFA.",
                "title": "Trajet du transfert",
                "rows": [{"label": "Solde après opération", "value": "94 850 FCFA"}],
                "targets": ["94 850 FCFA"],
            }
        ),
    )
    r_flow = client.post(
        "/answer",
        json={"transcript": "Combien il me restera après l'opération ?", "lang_hint": "fr", "context": review_ctx},
    )
    assert r_flow.status_code == 200
    acts_flow = r_flow.json()["actions"]
    nb_flow = next(a["action"] for a in acts_flow if a["action"]["t"] == "notebook")
    assert nb_flow["mode"] == "flow" and len(nb_flow["flow_steps"]) >= 2
    assert any(a["action"]["t"] == "callout" and a["action"]["target"]["node_id"] == "n_after" for a in acts_flow)

    # Bars sur "Compare mon solde et le montant"
    r_bars = client.post(
        "/answer",
        json={"transcript": "Compare mon solde et les frais", "lang_hint": "fr", "context": review_ctx},
    )
    assert r_bars.status_code == 200
    nb_bars = next(a["action"] for a in r_bars.json()["actions"] if a["action"]["t"] == "notebook")
    assert nb_bars["mode"] == "bars" and len(nb_bars["bars"]) >= 2


def test_harness_skips_redundant_notebook_on_single_target_and_uses_v12_gestures(monkeypatch):
    """Sobriété visuelle du harnais : 1 valeur ou 1 bouton = geste direct (circle/frame/highlight+check), sans tableau redondant."""
    from fastapi.testclient import TestClient
    from app.main import app

    class _FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    client = TestClient(app)

    simple_ctx = {
        "type": "screen_context",
        "app": {"package": "com.orange.maxit", "activity": "Home"},
        "channel": "mobile",
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_01", "tag": "span", "text": "Main Account", "clickable": False, "bounds": [60, 420, 300, 460], "tone": "dark"},
            {"node_id": "n_02", "tag": "span", "text": "24 828,58 FCFA", "clickable": False, "bounds": [60, 480, 340, 540], "tone": "dark"},
            {"node_id": "n_03", "tag": "button", "text": "Money transfer", "clickable": True, "bounds": [40, 920, 220, 1080], "tone": "dark"},
            {"node_id": "n_04", "tag": "span", "text": "Frais", "clickable": False, "bounds": [40, 1120, 180, 1160], "tone": "dark"},
            {"node_id": "n_05", "tag": "span", "text": "0 FCFA (Gratuit)", "clickable": False, "bounds": [220, 1120, 440, 1160], "tone": "dark"},
        ],
    }

    # 1. Solde unique -> circle sur 24 828,58 FCFA, PAS de notebook redondant
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResp({
            "spoken": "Ton solde disponible est de 24 828,58 FCFA.",
            "title": "Solde disponible",
            "rows": ["Solde disponible : 24 828,58 FCFA"],
            "targets": ["24 828,58 FCFA"],
            "color": "yellow",
        }),
    )
    r_bal = client.post("/answer", json={"transcript": "C'est quoi mon solde ?", "lang_hint": "fr", "context": simple_ctx})
    assert r_bal.status_code == 200
    t_bal = [a["action"]["t"] for a in r_bal.json()["actions"]]
    assert "notebook" not in t_bal and "arrow" not in t_bal and "circle" in t_bal

    # 2. Bouton unique -> frame sur Money transfer, PAS de notebook redondant
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResp({
            "spoken": "Appuie sur Money transfer pour envoyer de l'argent.",
            "title": "Envoyer de l'argent",
            "rows": ["Bouton : Money transfer"],
            "targets": ["Money transfer"],
            "color": "yellow",
        }),
    )
    r_btn = client.post("/answer", json={"transcript": "Comment envoyer de l'argent ?", "lang_hint": "fr", "context": simple_ctx})
    assert r_btn.status_code == 200
    t_btn = [a["action"]["t"] for a in r_btn.json()["actions"]]
    assert "notebook" not in t_btn and "frame" in t_btn

    # 3. Frais gratuits (0 FCFA) -> highlight + check vert, PAS de notebook redondant
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResp({
            "spoken": "Les frais sont gratuits, 0 FCFA.",
            "title": "Frais",
            "rows": ["Frais : 0 FCFA"],
            "targets": ["0 FCFA (Gratuit)"],
            "color": "green",
        }),
    )
    r_fee = client.post("/answer", json={"transcript": "Combien coûtent les frais ?", "lang_hint": "fr", "context": simple_ctx})
    assert r_fee.status_code == 200
    t_fee = [a["action"]["t"] for a in r_fee.json()["actions"]]
    assert "notebook" not in t_fee and "highlight" in t_fee and "check" in t_fee


def test_orthography_switch_cli_and_http():
    from app.sandbox.language import get_orthography_mode, set_orthography_mode
    from app.sandbox.orthography import main as ortho_cli

    prev = get_orthography_mode()
    try:
        payload = {
            "trace_id": "tr-ortho",
            "channel": "web",
            "type": "ui_translation",
            "language": "ewo",
            "source_language": "fr",
            "screen": "home",
            "strings": {
                "home.balance_label": {"text": "Solde disponible"},
                "shell.greeting": {"text": "Bonjour {name}"},
            },
        }
        # 1. Mode AGLC via CLI
        assert ortho_cli(["aglc"]) == 0
        r_aglc = client.post("/sandbox", json=payload)
        assert r_aglc.status_code == 200
        assert r_aglc.json()["strings"]["home.balance_label"] == "Itáŋ inə́ á ŋkwáp"
        assert r_aglc.json()["strings"]["shell.greeting"] == "Mbə̀mbə́ kírí {name}"

        # 2. Mode Assonance / Intuitif via CLI
        assert ortho_cli(["intuitive"]) == 0
        r_int = client.post("/sandbox", json=payload)
        assert r_int.status_code == 200
        assert r_int.json()["strings"]["home.balance_label"] == "Itan ineu a nkwap"
        assert r_int.json()["strings"]["shell.greeting"] == "{name} iyole dzoe Mbeumbe kiri"

        # 3. Bascule via HTTP POST /sandbox/orthography
        r_post = client.post("/sandbox/orthography", json={"mode": "aglc"})
        assert r_post.status_code == 200
        assert r_post.json()["mode"] == "aglc"
        r_back = client.post("/sandbox", json=payload)
        assert r_back.json()["strings"]["home.balance_label"] == "Itáŋ inə́ á ŋkwáp"
    finally:
        set_orthography_mode(prev)


def test_ussd_multiworker_sqlite_and_stateless_replica_recovery(tmp_path, monkeypatch):
    """Régression critique : les sessions USSD survivent entre workers distincts ET répliques stateless."""
    from app.sandbox import ussd_flow
    from app.sandbox.ussd_flow import SqliteSessionStore

    db_file = tmp_path / "sessions.sqlite3"
    worker1_store = SqliteSessionStore(db_file)
    worker2_store = SqliteSessionStore(db_file)

    bank = _mock_bank()

    def _benef_lookup(q: str | None = None, phone: str | None = None):
        ql = (q or "").lower()
        all_b = [
            {"name": "Blaise Mukete", "phone": "237621028428", "institution": "SAFINUM"},
            {"name": "Blaise Tchami", "phone": "237652084938", "institution": "SAFINUM"},
        ]
        if ql == "blaise":
            return True, 200, {"beneficiaries": all_b}
        if ql == "blaise mukete":
            # Simule même un backend qui ne matche pas l'espace -> fallback jetons + filtrage exact !
            return True, 200, {"beneficiaries": []}
        if ql == "mukete":
            return True, 200, {"beneficiaries": [all_b[0]]}
        return True, 200, {"beneficiaries": [b for b in all_b if ql in b["name"].lower()]}

    bank.beneficiaries.side_effect = _benef_lookup
    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-BLAISE-1", "amount": 5000, "fee": 50, "total": 5050, "to": "237652084938", "status": "pending"},
    )
    bank.confirm.return_value = (
        True,
        200,
        {"id": "TRX-BLAISE-1", "amount": 5000, "to": "237652084938", "status": "confirmed"},
    )

    # 1. Alternance Worker 1 / Worker 2 sur le parcours exact des captures utilisateur
    # Scénario A : saisie directe "Blaise Mukete" (en français et en ewondo) ne revient JAMAIS au menu !
    for lang in ("fr", "ewo"):
        sid = f"sess-full-{lang}"
        monkeypatch.setattr(ussd_flow, "SESSIONS", worker1_store)
        t1 = handle_channel_turn(
            {"session_id": sid, "channel": "ussd", "phone": "237652148466", "language": lang, "input": {"text": "", "ussd_text": ""}},
            bank_client=bank,
        )
        assert "1." in t1["response"]["text"]

        monkeypatch.setattr(ussd_flow, "SESSIONS", worker2_store)
        t2 = handle_channel_turn(
            {"session_id": sid, "channel": "ussd", "phone": "237652148466", "language": lang, "input": {"text": "2", "ussd_text": "2"}},
            bank_client=bank,
        )
        assert t2["interpretation"]["intent"] == "CLARIFICATION_NEEDED"

        # Worker 1 reprend la main : doit demander le montant (et JAMAIS réafficher le menu principal !)
        monkeypatch.setattr(ussd_flow, "SESSIONS", worker1_store)
        t3 = handle_channel_turn(
            {"session_id": sid, "channel": "ussd", "phone": "237652148466", "language": lang, "input": {"text": "Blaise Mukete", "ussd_text": "2*Blaise Mukete"}},
            bank_client=bank,
        )
        assert "fcfa" in t3["response"]["text"].lower(), f"Attendu demande montant, reçu: {t3['response']['text']!r}"
        assert "1. Mon solde" not in t3["response"]["text"] and "1. Itan" not in t3["response"]["text"]

    # Scénario B : homonyme "Blaise" -> choix "2" (Blaise Tchami) -> "5000" -> confirmation "1" sur un AUTRE worker !
    sid_b = "sess-confirm-multiworker"
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker1_store)
    handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "", "ussd_text": ""}}, bank_client=bank)
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker2_store)
    handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "2", "ussd_text": "2"}}, bank_client=bank)
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker1_store)
    r_amb = handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "Blaise", "ussd_text": "2*Blaise"}}, bank_client=bank)
    assert "Blaise Mukete" in r_amb["response"]["text"] and "Blaise Tchami" in r_amb["response"]["text"]
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker2_store)
    r_pick = handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "2", "ussd_text": "2*Blaise*2"}}, bank_client=bank)
    assert "montant" in r_pick["response"]["text"].lower()
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker1_store)
    r_recap = handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "5000", "ussd_text": "2*Blaise*2*5000"}}, bank_client=bank)
    assert "Blaise Tchami" in r_recap["response"]["text"] and "5 000 FCFA" in r_recap["response"]["text"]
    monkeypatch.setattr(ussd_flow, "SESSIONS", worker2_store)
    r_conf = handle_channel_turn({"session_id": sid_b, "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "1", "ussd_text": "2*Blaise*2*5000*1"}}, bank_client=bank)
    assert r_conf["interpretation"]["intent"] == "CONFIRM"
    assert r_conf["transaction"]["status"] == "confirmed"
    assert r_conf["response"]["end_session"] is True
    bank.confirm.assert_called_with("TRX-BLAISE-1")

    # 2. Scénario C : réplique totalement stateless (disque VIDE) au moment de la confirmation "1"
    # Doit rejouer en lecture seule + retrouver TRX-BLAISE-1 via history() SANS jamais recréer un second POST /transactions !
    replica_empty = SqliteSessionStore(tmp_path / "replica2.sqlite3")
    monkeypatch.setattr(ussd_flow, "SESSIONS", replica_empty)
    bank.create_transaction.reset_mock()
    bank.confirm.reset_mock()
    bank.history.return_value = (
        True,
        200,
        {
            "transactions": [
                {"id": "TRX-BLAISE-1", "type": "transfer", "amount": 5000, "fee": 50, "total": 5050, "to": "237652084938", "status": "pending"}
            ]
        },
    )
    r_recov = handle_channel_turn(
        {
            "session_id": "sess-replica-lost",
            "channel": "ussd",
            "phone": "237652148466",
            "language": "fr",
            "input": {"text": "1", "ussd_text": "2*Blaise*2*5000*1"},
        },
        bank_client=bank,
    )
    assert r_recov["interpretation"]["intent"] == "CONFIRM"
    assert r_recov["transaction"]["id"] == "TRX-BLAISE-1"
    assert r_recov["transaction"]["status"] == "confirmed"
    assert bank.create_transaction.call_count == 0
    bank.confirm.assert_called_once_with("TRX-BLAISE-1")


def test_ussd_name_collisions_parsing_and_all_flows():
    """Audit complet USSD : collisions de noms camerounais, langue, terminologie, 7 menus, annulation, ATM et GSM-7."""
    from app.sandbox.language import (
        PHRASES,
        detect_intent_keyword,
        detect_language_switch,
        detect_term_question,
        parse_amount,
        parse_phone,
        render_phrase,
    )

    # 1. Zéro faux positif de mots-clés sur les noms camerounais courants
    for safe_name in ("Louis", "Okala", "Mokom", "Kemogne", "Ndengue", "Ndongo", "Salome", "Gaetan", "Bille", "Blaise Mukete"):
        assert detect_intent_keyword(safe_name) is None, f"Faux positif intent sur {safe_name!r}"
        assert detect_language_switch(safe_name) is None, f"Faux positif langue sur {safe_name!r}"

    # 2. "en " en français ne doit JAMAIS basculer en anglais !
    assert detect_language_switch("envoyer 5000 en fcfa") is None
    assert detect_language_switch("frais en fcfa") is None
    assert detect_language_switch("passer en fulfulde") is None
    assert detect_language_switch("passer en ewondo") == "ewo"
    assert detect_language_switch("en duala") == "dua"
    assert detect_language_switch("en anglais") == "en"
    assert detect_language_switch("en") == "en"

    # 3. Priorité CORRECTION avant CANCEL/CONFIRM et non-détournement par detect_term_question
    assert detect_intent_keyword("non finalement 5000") == "CORRECTION"
    assert detect_intent_keyword("modifier beneficiaire Franck") == "CORRECTION"
    assert detect_term_question("modifier beneficiaire Franck") is None
    assert detect_term_question("Paul Ndongo", allow_bare=False) is None
    assert detect_term_question("c'est quoi un plafond ?") == "limit"

    # 4. Parsing montant/téléphone avec espaces/tirets
    assert parse_phone("+237 652 08 49 38") == "237652084938"
    assert parse_phone("621028428000") is None  # 12 chiffres invalides
    assert parse_amount("envoyer au 652 08 49 38") is None
    assert parse_amount("envoyer 5000 au 652 08 49 38") == 5000
    assert parse_amount("envoyer au 652-08-49-38") is None

    # 5. Tous les gabarits PHRASES en 4 langues respectent GSM-7 strict <= 182 septets
    sample_kw = {
        "phone": "652148466",
        "balance": "120 000 FCFA",
        "amount": "500 000 FCFA",
        "fee": "5 000 FCFA",
        "total": "505 000 FCFA",
        "to": "Jean-Baptiste Mukete",
        "operator": "ORANGE",
        "biller": "CAMWATER",
        "ref": "TRX-2026-000123",
        "choices": "1. Blaise Mukete (621028428)\n2. Blaise Tchami (652084938)",
        "resume": "Nom ou numero du beneficiaire:",
    }
    for key, langs in PHRASES.items():
        for lc in ("fr", "en", "ewo", "dua"):
            assert lc in langs, f"Langue {lc} manquante pour PHRASES[{key!r}]"
            rendered, declared = render_phrase(key, lc, max_septets=182, **sample_kw)
            assert declared == lc
            assert is_gsm7(rendered), f"Hors GSM-7 sur {key}.{lc}: {rendered!r}"
            assert gsm7_length(rendered) <= 182, f"Dépassement 182 septets sur {key}.{lc}: {gsm7_length(rendered)}"

    # 6. Flux complets : "je veux envoyer 5000 a Paul Ndongo", correction "modifier destinataire", annulation "sumua" en Duala,
    #    retour menu "0", changement de langue en plein transfert (garde l'étape!), crédit, facture, termes, ATM.
    SESSIONS.clear()
    bank = _mock_bank()
    bank.beneficiaries.return_value = (True, 200, {"beneficiaries": [{"name": "Paul Ndongo", "phone": "237699000010"}]})
    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-NDONGO", "amount": 5000, "fee": 50, "total": 5050, "to": "237699000010", "status": "pending"},
    )

    # Phrase naturelle complète avec "je veux envoyer" + nom contenant "Ndongo"
    r_nl = handle_channel_turn(
        {"session_id": "s_nl", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "je veux envoyer 5000 a Paul Ndongo"}},
        bank_client=bank,
    )
    assert r_nl["interpretation"]["intent"] == "TRANSFER"
    assert "Paul Ndongo" in r_nl["response"]["text"]

    # "modifier destinataire" (sans nom) -> demande le nouveau destinataire (PAS le montant!)
    r_md = handle_channel_turn(
        {"session_id": "s_nl", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "modifier destinataire"}},
        bank_client=bank,
    )
    assert r_md["interpretation"]["intent"] == "CORRECTION"
    assert "destinataire" in r_md["response"]["text"].lower()

    # "annuler" pendant correction_beneficiary -> annule proprement TRX-NDONGO (ne cherche pas un bénéficiaire "annuler")
    r_can = handle_channel_turn(
        {"session_id": "s_nl", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "annuler"}},
        bank_client=bank,
    )
    assert r_can["interpretation"]["intent"] == "CANCEL"
    assert r_can["response"]["end_session"] is True
    bank.cancel.assert_called_with("TRX-NDONGO")

    # Annulation en Duala avec "sumua" sur l'écran de confirmation
    SESSIONS.clear()
    bank.cancel.reset_mock()
    handle_channel_turn(
        {"session_id": "s_dua_can", "channel": "ussd", "phone": "237652148466", "language": "dua", "input": {"text": "loma 5000 o Paul Ndongo"}},
        bank_client=bank,
    )
    r_sumua = handle_channel_turn(
        {"session_id": "s_dua_can", "channel": "ussd", "phone": "237652148466", "language": "dua", "input": {"text": "sumua"}},
        bank_client=bank,
    )
    assert r_sumua["interpretation"]["intent"] == "CANCEL"
    assert r_sumua["response"]["end_session"] is True
    bank.cancel.assert_called_with("TRX-NDONGO")

    # Changement de langue en plein transfert_to garde l'étape transfer_to et réaffiche l'invite en ewondo !
    SESSIONS.clear()
    handle_channel_turn({"session_id": "s_sw_mid", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "2"}}, bank_client=bank)
    r_sw_mid = handle_channel_turn({"session_id": "s_sw_mid", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "passer en ewondo"}}, bank_client=bank)
    assert r_sw_mid["interpretation"]["intent"] == "LANGUAGE_SWITCH"
    assert r_sw_mid["interpretation"]["language"] == "ewo"
    assert "dzo" in r_sw_mid["response"]["text"].lower()  # invite beneficiaire en ewondo, pas le menu !
    r_after_sw = handle_channel_turn({"session_id": "s_sw_mid", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "Paul Ndongo"}}, bank_client=bank)
    assert "fcfa" in r_after_sw["response"]["text"].lower()
    # "0" retourne proprement au menu
    r_back0 = handle_channel_turn({"session_id": "s_sw_mid", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "0"}}, bank_client=bank)
    assert "1." in r_back0["response"]["text"] and "2." in r_back0["response"]["text"]

    # Menus 4 (Historique), 5 (Crédit), 6 (Facture), 7 (Termes), ATM (Retrait)
    SESSIONS.clear()
    r_h = handle_channel_turn({"session_id": "s_h", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "4"}}, bank_client=bank)
    assert r_h["interpretation"]["intent"] == "TRANSACTION_HISTORY" and r_h["response"]["end_session"] is True

    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-AIR", "amount": 1000, "fee": 0, "total": 1000, "operator": "MTN", "to": "237652148466", "status": "pending"},
    )
    handle_channel_turn({"session_id": "s_air", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "5"}}, bank_client=bank)
    handle_channel_turn({"session_id": "s_air", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "1"}}, bank_client=bank)
    r_air = handle_channel_turn({"session_id": "s_air", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "1000"}}, bank_client=bank)
    assert r_air["interpretation"]["intent"] == "AIRTIME_PURCHASE" and "MTN" in r_air["response"]["text"]

    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-BILL", "amount": 15000, "fee": 100, "total": 15100, "biller": "ENEO", "status": "pending"},
    )
    handle_channel_turn({"session_id": "s_bill", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "6"}}, bank_client=bank)
    handle_channel_turn({"session_id": "s_bill", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "1"}}, bank_client=bank)
    r_bill = handle_channel_turn({"session_id": "s_bill", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "15000"}}, bank_client=bank)
    assert r_bill["interpretation"]["intent"] == "BILL_PAYMENT" and "ENEO" in r_bill["response"]["text"]

    handle_channel_turn({"session_id": "s_t", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "7"}}, bank_client=bank)
    r_t_bad = handle_channel_turn({"session_id": "s_t", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "9"}}, bank_client=bank)
    assert r_t_bad["interpretation"]["intent"] == "CLARIFICATION_NEEDED"
    r_t_ok = handle_channel_turn({"session_id": "s_t", "channel": "ussd", "phone": "237652148466", "language": "fr", "input": {"text": "2"}}, bank_client=bank)
    assert r_t_ok["interpretation"]["intent"] == "TERM_EXPLANATION" and "500 000 FCFA" in r_t_ok["response"]["text"]

    bank.create_transaction.return_value = (
        True,
        201,
        {"id": "TRX-ATM", "amount": 10000, "fee": 150, "total": 10150, "status": "pending"},
    )
    r_atm = handle_channel_turn({"session_id": "s_atm", "channel": "atm", "phone": "237652148466", "language": "fr", "input": {"text": "10000"}}, bank_client=bank)
    assert "Retrait GAB 10 000 FCFA" in r_atm["response"]["text"]
    assert "Modifier destinataire" not in r_atm["response"]["options"]


