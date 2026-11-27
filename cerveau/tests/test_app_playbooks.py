from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"response": json.dumps(self._payload, ensure_ascii=False)}


# Arbre d'accessibilité RÉEL capturé sur Wave Android (com.wave.personal) via uiautomator dump
# Note : volontairement dans l'ordre XML réel où la liste de transactions arrive AVANT le solde du haut !
WAVE_REAL_CTX = {
    "type": "screen_context",
    "app": {"package": "com.wave.personal", "activity": "PersonalHomeActivity"},
    "channel": "mobile",
    "screen_hint": "home",
    "nodes": [
        {"node_id": "n_01", "tag": "span", "text": "Send", "clickable": False, "bounds": [82, 721, 138, 750], "tone": "unknown"},
        {"node_id": "n_02", "tag": "span", "text": "Bills", "clickable": False, "bounds": [254, 721, 301, 750], "tone": "unknown"},
        {"node_id": "n_03", "tag": "span", "text": "Vault", "clickable": False, "bounds": [415, 721, 472, 750], "tone": "unknown"},
        {"node_id": "n_04", "tag": "span", "text": "More", "clickable": False, "bounds": [582, 721, 639, 750], "tone": "unknown"},
        {"node_id": "n_05", "tag": "span", "text": "GIMAC transfer from WILFRIED FOKAM DE LOKA", "clickable": False, "bounds": [28, 834, 589, 900], "tone": "unknown"},
        {"node_id": "n_06", "tag": "span", "text": "1.500F", "clickable": False, "bounds": [603, 834, 692, 867], "tone": "unknown"},
        {"node_id": "n_07", "tag": "span", "text": "Nov 27, 12:10", "clickable": False, "bounds": [28, 900, 172, 929], "tone": "unknown"},
        {"node_id": "n_08", "tag": "span", "text": "Settings", "clickable": False, "bounds": [32, 104, 67, 139], "tone": "unknown"},
        {"node_id": "n_09", "tag": "span", "text": "1.500F", "clickable": False, "bounds": [263, 157, 458, 229], "tone": "unknown"},
        {"node_id": "n_10", "tag": "span", "text": "Hide balance", "clickable": False, "bounds": [472, 186, 505, 214], "tone": "unknown"},
    ],
}

# Écran RÉEL `banque-demo.sandbox/transfer` en Ewondo (capture utilisateur)
SAFINUM_TRANSFER_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "beneficiary",
    "nodes": [
        {"node_id": "n_01", "tag": "h2", "text": "Envoyer de l'argent", "clickable": False, "bounds": [540, 220, 740, 250], "tone": "light"},
        {"node_id": "n_02", "tag": "label", "text": "Bénéficiaire", "clickable": False, "bounds": [560, 310, 680, 330], "tone": "light"},
        {"node_id": "n_03", "tag": "input", "text": "Numéro de téléphone ou nom", "clickable": False, "bounds": [560, 340, 820, 380], "tone": "light"},
        {"node_id": "n_04", "tag": "label", "text": "Montant", "clickable": False, "bounds": [560, 410, 650, 430], "tone": "light"},
        {"node_id": "n_05", "tag": "span", "text": "Jusqu'à 500 000 FCFA par opération", "clickable": False, "bounds": [560, 480, 820, 500], "tone": "light"},
        {"node_id": "n_06", "tag": "button", "text": "Annuler", "clickable": True, "bounds": [680, 520, 740, 555], "tone": "light"},
        {"node_id": "n_07", "tag": "button", "text": "Continuer", "clickable": True, "bounds": [750, 520, 850, 555], "tone": "light"},
        {"node_id": "n_08", "tag": "h3", "text": "Mes bénéficiaires", "clickable": False, "bounds": [900, 310, 1080, 335], "tone": "light"},
        {"node_id": "n_09", "tag": "button", "text": "Blaise Tchami", "clickable": True, "bounds": [900, 360, 1020, 385], "tone": "light"},
        {"node_id": "n_10", "tag": "span", "text": "237652084938", "clickable": False, "bounds": [1030, 360, 1140, 385], "tone": "light"},
    ],
}


def test_wave_real_screen_balance_and_beginner_scenarios(monkeypatch):
    # 1. Solde sur Wave -> entoure OBLIGATOIREMENT n_09 (solde du haut 1.500F, y=157) et JAMAIS n_06 (transaction y=834) ni "More" !
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResp({
            "spoken": "Ton solde disponible est de 1.500F.",
            "title": "Solde disponible",
            "rows": ["Solde disponible : 1.500F"],
            "targets": ["1.500F"],
            "color": "yellow",
        }),
    )
    r_bal = client.post("/answer", json={"transcript": "C'est quoi mon solde ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert r_bal.status_code == 200
    acts_bal = r_bal.json()["actions"]
    spoken_bal = " ".join(a["action"].get("text", "") for a in acts_bal if a["action"]["t"] == "speak")
    assert "more" not in spoken_bal.lower()
    circle_targets = [a["action"]["target"]["node_id"] for a in acts_bal if a["action"]["t"] in {"circle", "box"} and a["action"].get("target")]
    assert circle_targets == ["n_09"]
    assert all(a["action"]["t"] != "notebook" for a in acts_bal)

    # 2. "Comment envoyer de l'argent ?" sur Wave -> cadre directement `Send` (n_01), JAMAIS Hors contexte !
    r_send = client.post("/answer", json={"transcript": "Comment envoyer de l'argent ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert r_send.status_code == 200
    acts_send = r_send.json()["actions"]
    spoken_send = " ".join(a["action"].get("text", "") for a in acts_send if a["action"]["t"] == "speak").lower()
    assert "incapable" not in spoken_send and "hors contexte" not in spoken_send
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_01" for a in acts_send)

    # 3. Scénarios débutants Wave (QR code, Vault/Coffre, Bills, Hide balance, "Je dois faire quoi ici ?")
    r_qr = client.post("/answer", json={"transcript": "À quoi sert le QR code ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert "scanner" in " ".join(a["action"].get("text", "") for a in r_qr.json()["actions"] if a["action"]["t"] == "speak").lower()

    r_vault = client.post("/answer", json={"transcript": "C'est quoi Vault ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_03" for a in r_vault.json()["actions"])

    r_hide = client.post("/answer", json={"transcript": "Comment cacher mon solde ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert any(a["action"]["t"] == "circle" and a["action"]["target"]["node_id"] == "n_10" for a in r_hide.json()["actions"])

    r_guide = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    spoken_guide = " ".join(a["action"].get("text", "") for a in r_guide.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "wave" in spoken_guide and "qr code" in spoken_guide


def test_safinum_transfer_screen_guide_never_hallucinates_limit_or_contact():
    # 1. "Je dois faire quoi ici ?" sur /transfer -> guide en 3 étapes, JAMAIS "Tu dois envoyer 500 000 FCFA à Blaise Tchami" !
    r_guide = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    assert r_guide.status_code == 200
    acts = r_guide.json()["actions"]
    spoken = " ".join(a["action"].get("text", "") for a in acts if a["action"]["t"] == "speak").lower()
    assert "blaise" not in spoken and "500 000" not in spoken
    assert "bénéficiaire" in spoken and "montant" in spoken and "continuer" in spoken
    target_ids = [a["action"]["target"]["node_id"] for a in acts if a["action"].get("target")]
    assert "n_02" in target_ids and "n_04" in target_ids and "n_07" in target_ids

    # 2. Question débutant sur le plafond "500 000 FCFA"
    r_lim = client.post("/answer", json={"transcript": "Je dois envoyer 500 000 FCFA ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    spoken_lim = " ".join(a["action"].get("text", "") for a in r_lim.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "plafond" in spoken_lim or "maximum" in spoken_lim

    # 3. Question sur la liste de contacts enregistrés ("Mes bénéficiaires")
    r_list = client.post("/answer", json={"transcript": "C'est quoi la liste à droite avec Blaise Tchami ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    spoken_list = " ".join(a["action"].get("text", "") for a in r_list.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "contacts" in spoken_list or "enregistrés" in spoken_list

    # 4. Comment annuler -> cadre sur Annuler (n_06)
    r_cancel = client.post("/answer", json={"transcript": "Comment annuler si je me suis trompé ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_06" for a in r_cancel.json()["actions"])
