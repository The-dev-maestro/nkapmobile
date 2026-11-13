from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.core.contracts import ScreenContext
from app.main import app

client = TestClient(app)


def make_web_context_payload() -> dict:
    return {
        "type": "screen_context",
        "page": {
            "url": "https://safinum.cm/hackathon-test?jury=1",
            "title": "Safinum Pay — Démo",
        },
        "screen_hint": "home",
        "nodes": [
            {
                "node_id": "n_01",
                "tag": "p",
                "text": "Solde disponible",
                "clickable": False,
                "bounds": [40, 120, 180, 142],
                "tone": "dark",
            },
            {
                "node_id": "n_02",
                "tag": "p",
                "text": "250 000 FCFA",
                "clickable": False,
                "bounds": [40, 148, 210, 180],
                "tone": "dark",
            },
        ],
    }


def test_screen_context_accepts_i5_web_payload():
    model = ScreenContext.model_validate(make_web_context_payload())
    assert model.app is None
    assert model.page is not None
    assert "safinum.cm" in model.page.url
    assert model.nodes[1].tag == "p"
    assert model.nodes[1].path is None


def test_screen_context_requires_app_or_page():
    payload = make_web_context_payload()
    del payload["page"]
    with pytest.raises(ValueError, match="either 'app' .* or 'page'"):
        ScreenContext.model_validate(payload)


def test_http_answer_returns_validated_actions():
    with patch("app.llm.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "intent": "check_balance",
            "amount": "250 000 FCFA",
        }
        mock_post.return_value.raise_for_status = lambda: None

        resp = client.post(
            "/answer",
            json={
                "transcript": "Quel est mon solde ?",
                "lang_hint": "fr",
                "context": make_web_context_payload(),
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_id"].startswith("t_")
    action_types = [item["action"]["t"] for item in body["actions"]]
    assert action_types == ["speak", "circle", "write"]
    circle = next(item["action"] for item in body["actions"] if item["action"]["t"] == "circle")
    assert circle["target"]["node_id"] == "n_02"
    speak = next(item["action"] for item in body["actions"] if item["action"]["t"] == "speak")
    assert "250 000 FCFA" in speak["text"]


def test_http_answer_returns_422_harness_reject_on_unsafe_stream():
    with patch("app.main.service.handle_turn", side_effect=ValueError("Montant altéré")):
        resp = client.post(
            "/answer",
            json={
                "transcript": "Quel est mon solde ?",
                "lang_hint": "fr",
                "context": make_web_context_payload(),
            },
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "harness_reject"
    assert "Montant altéré" in resp.json()["reason"]


def test_http_answer_compiles_custom_llm_plan_and_guards_targets(monkeypatch):
    import json

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": {"content": json.dumps(self._payload, ensure_ascii=False)}}

    # 1. Schéma compact 6 clés : filtre les nœuds inventés et borne à <= 3 marques visuelles
    def fake_ollama_compact(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(
            {
                "spoken": "Regarde l'encadré Musango : vérifie toujours le nom et le numéro avant d'envoyer.",
                "title": "Vérifier avant envoi",
                "points": [
                    "• Contrôle le nom et le numéro",
                    "→ Lire la carte Musango",
                ],
                "targets": ["n_node_invente", "n_10", "n_11"],
                "style": "box",
                "color": "green",
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_ollama_compact)
    home_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_01", "tag": "h2", "text": "Bonjour, Amina", "clickable": False, "bounds": [0, 0, 180, 24], "tone": "dark"},
            {"node_id": "n_10", "tag": "h3", "text": "Musango [Sécurité]", "clickable": False, "bounds": [420, 240, 520, 265], "tone": "dark"},
            {"node_id": "n_11", "tag": "p", "text": "Ombwa bwam dina na nimero ya mukusa oboso ba bola loma.", "clickable": False, "bounds": [420, 270, 650, 310], "tone": "dark"},
        ],
    }
    resp = client.post(
        "/answer",
        json={"transcript": "Comment je sais si quelqu'un veut m'arnaquer ?", "lang_hint": "fr", "context": home_ctx},
    )
    assert resp.status_code == 200
    acts = resp.json()["actions"]
    types = [a["action"]["t"] for a in acts]
    assert types == ["speak", "notebook", "arrow", "box", "clear"]
    assert acts[0]["action"]["phrase_key"] == "llm_answer"
    assert acts[1]["action"]["title"] == "Vérifier avant envoi"
    assert "from" in acts[2]["action"] and "from_" not in acts[2]["action"]
    assert acts[2]["action"]["to"]["node_id"] == "n_10"
    assert acts[3]["action"]["target"]["node_id"] == "n_10"
    assert acts[3]["action"]["color"] == "green"
    # Aucun nœud halluciné + max 3 marques visuelles (notebook + arrow + box)
    target_ids = {
        a["action"].get("target", {}).get("node_id") or a["action"].get("to", {}).get("node_id")
        for a in acts
    }
    assert "n_node_invente" not in target_ids
    visual_marks = [a for a in acts if a["action"]["t"] in {"notebook", "arrow", "box", "circle", "frame", "underline", "write"}]
    assert len(visual_marks) <= 3

    # 2. Schéma détaillé rich-highlights (notebook_lines + highlights + spoken_after)
    def fake_ollama_rich(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(
            {
                "spoken": "Les frais affichés ici sont de 0 FCFA.",
                "notebook_title": "Frais du transfert",
                "notebook_lines": [
                    {"label": "Frais", "value": "0 FCFA", "color": "green"},
                    {"text": "→ Aucun frais prélevé", "underline": True},
                ],
                "highlights": [
                    {"node_id": "n_04", "style": "underline", "color": "green", "arrow_from_notebook": True}
                ],
                "spoken_after": "Tu peux continuer si le reste te convient.",
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_ollama_rich)
    fees_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "fees",
        "nodes": [
            {"node_id": "n_03", "tag": "span", "text": "Frais", "clickable": False, "bounds": [0, 80, 60, 100], "tone": "dark"},
            {"node_id": "n_04", "tag": "span", "text": "0 FCFA", "clickable": False, "bounds": [80, 80, 140, 100], "tone": "dark"},
        ],
    }
    resp_rich = client.post(
        "/answer",
        json={"transcript": "Combien coûtent les frais ?", "lang_hint": "fr", "context": fees_ctx},
    )
    assert resp_rich.status_code == 200
    acts_rich = resp_rich.json()["actions"]
    assert [a["action"]["t"] for a in acts_rich] == ["speak", "notebook", "arrow", "speak", "underline", "clear"]
    assert acts_rich[4]["action"]["target"]["node_id"] == "n_04"


def test_http_answer_handles_dynamic_offline_fallback(monkeypatch):
    def fake_failing_post(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr("app.llm.requests.post", fake_failing_post)

    # 1. Repli hors-ligne ancré sur l'écran réel : frais (associe libellé + valeur suivante)
    fees_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "fees",
        "nodes": [
            {"node_id": "n_01", "tag": "p", "text": "Solde disponible", "clickable": False, "bounds": [0, 0, 100, 20], "tone": "dark"},
            {"node_id": "n_02", "tag": "p", "text": "250 000 FCFA", "clickable": False, "bounds": [0, 25, 100, 45], "tone": "dark"},
            {"node_id": "n_03", "tag": "span", "text": "Frais", "clickable": False, "bounds": [0, 80, 60, 100], "tone": "dark"},
            {"node_id": "n_04", "tag": "span", "text": "0 FCFA", "clickable": False, "bounds": [80, 80, 140, 100], "tone": "dark"},
        ],
    }
    resp_fees = client.post(
        "/answer",
        json={"transcript": "Combien coûtent les frais ?", "lang_hint": "fr", "context": fees_ctx},
    )
    assert resp_fees.status_code == 200
    acts_fees = resp_fees.json()["actions"]
    assert [a["action"]["t"] for a in acts_fees] == ["speak", "notebook", "arrow", "box", "clear"]
    assert "0 FCFA" in acts_fees[0]["action"]["text"]
    assert acts_fees[3]["action"]["target"]["node_id"] == "n_04"

    # 2. Pas de fausse alerte inventée hors-ligne si aucun bandeau d'avertissement n'est affiché
    home_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_01", "tag": "h2", "text": "Bonjour, Amina", "clickable": False, "bounds": [0, 0, 180, 24], "tone": "dark"},
            {"node_id": "n_10", "tag": "h3", "text": "Musango [Sécurité]", "clickable": False, "bounds": [420, 240, 520, 265], "tone": "dark"},
        ],
    }
    resp_home = client.post(
        "/answer",
        json={"transcript": "Pourquoi cette alerte jaune ?", "lang_hint": "fr", "context": home_ctx},
    )
    assert resp_home.status_code == 200
    spoken_home = resp_home.json()["actions"][0]["action"]["text"].lower()
    assert "message jaune" not in spoken_home

    # 3. Erreur bloquante affichée à l'écran -> encadré rouge dynamique
    err_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "beneficiary",
        "nodes": [
            {"node_id": "n_e1", "tag": "div", "text": "Une erreur est survenue : Solde insuffisant pour effectuer ce transfert.", "clickable": False, "bounds": [0, 0, 320, 40], "tone": "dark"},
        ],
    }
    resp_err = client.post(
        "/answer",
        json={"transcript": "Pourquoi cette erreur ?", "lang_hint": "fr", "context": err_ctx},
    )
    assert resp_err.status_code == 200
    assert any(
        a["action"]["t"] == "box" and a["action"].get("color") == "red"
        for a in resp_err.json()["actions"]
    )

    # 4. Question libre sur le numéro de compte affiché
    custom_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_h1", "tag": "p", "text": "Amina Ngo Bell", "clickable": False, "bounds": [0, 0, 180, 24], "tone": "dark"},
            {"node_id": "n_h2", "tag": "p", "text": "Numéro de compte : CM 001 2345 6789 01", "clickable": False, "bounds": [0, 30, 260, 50], "tone": "dark"},
        ],
    }
    resp_custom = client.post(
        "/answer",
        json={"transcript": "Quel est mon numéro de compte CM ?", "lang_hint": "fr", "context": custom_ctx},
    )
    assert resp_custom.status_code == 200
    acts_custom = resp_custom.json()["actions"]
    assert any(a["action"]["t"] == "notebook" for a in acts_custom)
    assert any(a["action"].get("target", {}).get("node_id") == "n_h2" for a in acts_custom)


def test_http_answer_spatial_row_grouping_and_target_text_resolution(monkeypatch):
    import json

    captured_prompts = []

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    # 1. Écran frais en Douala : `Mabála | Bonam | 0 FCFA` sur la même ligne Y que `Botali ba busa | 25 000 FCFA`
    def fake_ollama_target_text(url, json=None, timeout=None, **kwargs):
        captured_prompts.append(json.get("prompt", ""))
        return _FakeResponse(
            {
                "spoken": "Les frais de transfert sont de 0 FCFA.",
                "title": "Frais de transfert",
                "points": [
                    "Compte Safinum sans frais",
                    "→ Frais affichés : 0 FCFA",
                ],
                "target_text": "0 FCFA",
                "style": "underline",
                "color": "yellow",
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_ollama_target_text)
    real_fees_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum Pay"},
        "screen_hint": "fees",
        "nodes": [
            {"node_id": "n_ban", "tag": "div", "text": "Environnement de test — données fictives", "clickable": False, "bounds": [0, 0, 1000, 32], "tone": "light"},
            {"node_id": "n_app", "tag": "span", "text": "Safinum Pay", "clickable": False, "bounds": [160, 50, 280, 75], "tone": "dark"},
            {"node_id": "n_f1", "tag": "span", "text": "Mabála", "clickable": False, "bounds": [180, 580, 235, 600], "tone": "dark"},
            {"node_id": "n_f2", "tag": "span", "text": "Bonam", "clickable": False, "bounds": [245, 580, 295, 600], "tone": "dark"},
            {"node_id": "n_f3", "tag": "span", "text": "0 FCFA", "clickable": False, "bounds": [530, 580, 585, 600], "tone": "dark"},
            {"node_id": "n_t1", "tag": "span", "text": "Botali ba busa", "clickable": False, "bounds": [180, 620, 290, 640], "tone": "dark"},
            {"node_id": "n_t2", "tag": "span", "text": "25 000 FCFA", "clickable": False, "bounds": [510, 620, 585, 640], "tone": "dark"},
            # Panneau latéral (Y remonte de 620 -> 220)
            {"node_id": "n_s1", "tag": "span", "text": "MONI MA PEŃE", "clickable": False, "bounds": [680, 220, 780, 240], "tone": "dark"},
            {"node_id": "n_s2", "tag": "span", "text": "250 000 FCFA", "clickable": False, "bounds": [680, 250, 810, 280], "tone": "dark"},
        ],
    }
    resp = client.post(
        "/answer",
        json={"transcript": "Quels sont les frais de transfert ?", "lang_hint": "fr", "context": real_fees_ctx},
    )
    assert resp.status_code == 200
    assert captured_prompts
    # Le bandeau test est exclu, le contexte est 100 % en français sans Douala/Ewondo, et chaque ligne est regroupée
    assert "Environnement de test" not in captured_prompts[0]
    assert "Mabála" not in captured_prompts[0]
    assert "MONI MA PEŃE" not in captured_prompts[0]
    assert "- Frais | Gratuit | 0 FCFA" in captured_prompts[0]
    assert "- Total à débiter | 25 000 FCFA" in captured_prompts[0]
    assert "Panneau latéral:" in captured_prompts[0]
    acts = resp.json()["actions"]
    assert acts[-2]["action"]["target"]["node_id"] == "n_f3"

    # 2. Doublon solde `250 000 FCFA` (zone principale vs sidebar) + sous-titre décoratif : pointe toujours la zone principale
    def fake_ollama_balance(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(
            {
                "spoken": "Ton solde est de 250 000 FCFA.",
                "title": "Solde",
                "points": ["Solde disponible", "250 000 FCFA"],
                "target_text": "250 000 FCFA",
                "style": "underline",
                "color": "yellow",
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_ollama_balance)
    dup_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum Pay"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_sub", "tag": "p", "text": "Ombwa moni mango pe loma moni na musango.", "clickable": False, "bounds": [180, 210, 500, 232], "tone": "dark"},
            {"node_id": "n_lbl", "tag": "span", "text": "MONI MA PEŃE", "clickable": False, "bounds": [180, 260, 290, 280], "tone": "dark"},
            {"node_id": "n_main_bal", "tag": "p", "text": "250 000 FCFA", "clickable": False, "bounds": [180, 290, 360, 330], "tone": "dark"},
            {"node_id": "n_side_lbl", "tag": "span", "text": "MONI MA PEŃE", "clickable": False, "bounds": [680, 210, 780, 230], "tone": "dark"},
            {"node_id": "n_side_bal", "tag": "p", "text": "250 000 FCFA", "clickable": False, "bounds": [680, 240, 810, 270], "tone": "dark"},
        ],
    }
    resp_bal = client.post(
        "/answer",
        json={"transcript": "Quel est mon solde ?", "lang_hint": "fr", "context": dup_ctx},
    )
    assert resp_bal.status_code == 200
    acts_bal = resp_bal.json()["actions"]
    assert acts_bal[-2]["action"]["target"]["node_id"] == "n_main_bal"


def test_http_answer_compiles_fast_two_key_llm_payload(monkeypatch):
    import json

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    def fake_ollama_two_keys(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(
            {
                "spoken": "Envoie de l'argent",
                "targets": ["Envoyer de l'argent"],
            }
        )

    monkeypatch.setattr("app.llm.requests.post", fake_ollama_two_keys)
    btn_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum Pay"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_lbl", "tag": "p", "text": "Solde disponible", "clickable": False, "bounds": [40, 120, 180, 142], "tone": "dark"},
            {"node_id": "n_bal", "tag": "p", "text": "250 000 FCFA", "clickable": False, "bounds": [40, 148, 210, 180], "tone": "dark"},
            {"node_id": "n_send", "tag": "button", "text": "Envoyer de l'argent", "clickable": True, "bounds": [80, 360, 300, 410], "tone": "dark"},
        ],
    }
    resp = client.post(
        "/answer",
        json={"transcript": "Comment envoyer de l'argent ?", "lang_hint": "fr", "context": btn_ctx},
    )
    assert resp.status_code == 200
    acts = resp.json()["actions"]
    types = [a["action"]["t"] for a in acts]
    assert types == ["speak", "frame", "clear"]
    assert "Envoyer de l'argent" in acts[0]["action"]["text"]
    assert acts[1]["action"]["target"]["node_id"] == "n_send"


def test_http_answer_guards_greeting_transfer_arrow_and_fees_confusion(monkeypatch):
    import json

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": json.dumps(self._payload, ensure_ascii=False)}

    # 1. Salutation pure ("bonjour") -> speak uniquement sans LLM ni carnet
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Le LLM ne doit pas être appelé pour un simple bonjour")

    monkeypatch.setattr("app.llm.requests.post", fail_if_called)
    home_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum Pay"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "n_name", "tag": "span", "text": "Amina Ngo Bell", "clickable": False, "bounds": [700, 20, 880, 44], "tone": "dark"},
            {"node_id": "n_vc", "tag": "span", "text": "VOTRE COMPTE", "clickable": False, "bounds": [80, 140, 200, 160], "tone": "dark"},
            {"node_id": "n_bjr", "tag": "h2", "text": "Bonjour, Amina", "clickable": False, "bounds": [80, 168, 280, 204], "tone": "dark"},
            {"node_id": "n_trf", "tag": "button", "text": "Effectuer un transfert", "clickable": True, "bounds": [80, 340, 280, 388], "tone": "dark"},
        ],
    }
    resp_hi = client.post("/answer", json={"transcript": "bonjour", "lang_hint": "fr", "context": home_ctx})
    assert resp_hi.status_code == 200
    assert [a["action"]["t"] for a in resp_hi.json()["actions"]] == ["speak", "clear"]

    # 2. "comment faire un transfert" avec cible parasite ("Amina Ngo Bell") -> pas de flèche depuis le nom, cadre sur le bouton
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResponse({"spoken": "Appuie sur Effectuer un transfert.", "targets": ["Amina Ngo Bell", "Effectuer un transfert"]}),
    )
    resp_trf = client.post("/answer", json={"transcript": "comment faire un transfert", "lang_hint": "fr", "context": home_ctx})
    assert resp_trf.status_code == 200
    trf_acts = resp_trf.json()["actions"]
    assert [a["action"]["t"] for a in trf_acts] == ["speak", "frame", "clear"]
    assert trf_acts[1]["action"]["target"]["node_id"] == "n_trf"

    # 3. Question sur les frais mais le petit LLM répond "Total à débiter : 25 000 FCFA" -> recadré sur Frais (0 FCFA)
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResponse({"spoken": "Le total à débiter est de 25 000 FCFA.", "targets": ["25 000 FCFA"]}),
    )
    fees_ctx = {
        "type": "screen_context",
        "page": {"url": "https://safinum.cm/hackathon-test", "title": "Safinum Pay"},
        "screen_hint": "fees",
        "nodes": [
            {"node_id": "n_flbl", "tag": "span", "text": "Frais", "clickable": False, "bounds": [80, 380, 140, 400], "tone": "dark"},
            {"node_id": "n_fgrat", "tag": "span", "text": "Gratuit", "clickable": False, "bounds": [150, 380, 210, 400], "tone": "dark"},
            {"node_id": "n_fval", "tag": "span", "text": "0 FCFA", "clickable": False, "bounds": [480, 380, 560, 400], "tone": "dark"},
            {"node_id": "n_tlbl", "tag": "span", "text": "Total à débiter", "clickable": False, "bounds": [80, 420, 220, 444], "tone": "dark"},
            {"node_id": "n_tval", "tag": "span", "text": "25 000 FCFA", "clickable": False, "bounds": [450, 420, 560, 444], "tone": "dark"},
        ],
    }
    resp_fee = client.post("/answer", json={"transcript": "quels sont les frais ?", "lang_hint": "fr", "context": fees_ctx})
    assert resp_fee.status_code == 200
    fee_acts = resp_fee.json()["actions"]
    assert "0 FCFA" in fee_acts[0]["action"]["text"]
    assert "25 000 FCFA" not in fee_acts[0]["action"]["text"]
    box_act = next(a["action"] for a in fee_acts if a["action"]["t"] == "box")
    assert box_act["target"]["node_id"] == "n_fval"

    # 4. Question sur les frais mais le LLM renvoie les 2 cibles ("0 FCFA" ET "25 000 FCFA") -> garde uniquement "0 FCFA"
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResponse({"spoken": "Les frais sont de 0 FCFA.", "targets": ["0 FCFA", "25 000 FCFA"]}),
    )
    resp_fee2 = client.post("/answer", json={"transcript": "quels sont les frais ?", "lang_hint": "fr", "context": fees_ctx})
    assert resp_fee2.status_code == 200
    fee_boxes2 = [a["action"] for a in resp_fee2.json()["actions"] if a["action"]["t"] == "box"]
    assert len(fee_boxes2) == 1
    assert fee_boxes2[0]["target"]["node_id"] == "n_fval"


