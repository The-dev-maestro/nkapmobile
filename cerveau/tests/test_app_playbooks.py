from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app.core.app_kb import AppPlaybookStore
from app.core.contracts import ScreenNode
from app.main import app


client = TestClient(app)


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"response": json.dumps(self._payload, ensure_ascii=False)}


# ── WAVE : écrans réels capturés sur TECNO KN4 (com.wave.personal) ──────────

# 1. Wave Home (ordre XML réel où la liste de transactions arrive AVANT le solde du haut !)
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

# 2. Wave Send Money (écran réel des captures utilisateur : ← Send Money / To / Enter a new number / Scan to send / Contacts)
WAVE_SEND_MONEY_CTX = {
    "type": "screen_context",
    "app": {"package": "com.wave.personal", "activity": "PersonalHomeActivity"},
    "channel": "mobile",
    "screen_hint": "home",
    "nodes": [
        {"node_id": "w_back", "tag": "span", "text": "", "content_desc": "Back", "clickable": True, "bounds": [28, 96, 76, 144], "tone": "light"},
        {"node_id": "w_title", "tag": "span", "text": "Send Money", "clickable": False, "bounds": [126, 98, 344, 146], "tone": "light"},
        {"node_id": "w_to", "tag": "span", "text": "To", "clickable": False, "bounds": [28, 194, 72, 224], "tone": "light"},
        {"node_id": "w_new", "tag": "span", "text": "Enter a new number", "clickable": False, "bounds": [132, 316, 420, 360], "tone": "light"},
        {"node_id": "w_scan", "tag": "span", "text": "Scan to send", "clickable": False, "bounds": [132, 444, 330, 488], "tone": "light"},
        {"node_id": "w_contacts", "tag": "span", "text": "Contacts", "clickable": False, "bounds": [28, 566, 178, 604], "tone": "light"},
        {"node_id": "w_c1", "tag": "span", "text": ".Djunette", "clickable": False, "bounds": [126, 650, 290, 684], "tone": "light"},
        {"node_id": "w_c1n", "tag": "span", "text": "680 78 18 01", "clickable": False, "bounds": [126, 690, 310, 720], "tone": "light"},
    ],
}

# 3. Wave Send Amount
WAVE_SEND_AMOUNT_CTX = {
    "type": "screen_context",
    "app": {"package": "com.wave.personal", "activity": "SendAmountActivity"},
    "channel": "mobile",
    "screen_hint": "home",
    "nodes": [
        {"node_id": "wa_back", "tag": "span", "text": "", "content_desc": "Back", "clickable": True, "bounds": [28, 96, 76, 144], "tone": "light"},
        {"node_id": "wa_title", "tag": "span", "text": "Send Money", "clickable": False, "bounds": [126, 98, 344, 146], "tone": "light"},
        {"node_id": "wa_sa", "tag": "span", "text": "Send Amount", "clickable": False, "bounds": [32, 320, 260, 360], "tone": "light"},
        {"node_id": "wa_ra", "tag": "span", "text": "Receive Amount", "clickable": False, "bounds": [32, 460, 280, 500], "tone": "light"},
        {"node_id": "wa_btn", "tag": "button", "text": "Send", "clickable": True, "bounds": [60, 1360, 660, 1450], "tone": "light"},
    ],
}

# 4. Wave Vault / Bills / Settings / Fullscreen QR
WAVE_VAULT_CTX = {
    "type": "screen_context",
    "app": {"package": "com.wave.personal", "activity": "VaultActivity"},
    "channel": "mobile",
    "screen_hint": "home",
    "nodes": [
        {"node_id": "wv_back", "tag": "span", "text": "", "content_desc": "Back", "clickable": True, "bounds": [28, 96, 76, 144], "tone": "light"},
        {"node_id": "wv_title", "tag": "span", "text": "My Vault", "clickable": False, "bounds": [126, 98, 300, 146], "tone": "light"},
        {"node_id": "wv_tr", "tag": "button", "text": "Transfer to Vault", "clickable": True, "bounds": [40, 500, 680, 570], "tone": "light"},
        {"node_id": "wv_wd", "tag": "button", "text": "Withdraw from Vault", "clickable": True, "bounds": [40, 600, 680, 670], "tone": "light"},
    ],
}

WAVE_CARD_QR_CTX = {
    "type": "screen_context",
    "app": {"package": "com.wave.personal", "activity": "com.wave.customer.CardFullScreenActivity"},
    "channel": "mobile",
    "screen_hint": "home",
    "nodes": [
        {"node_id": "wq_back", "tag": "span", "text": "", "content_desc": "Back", "clickable": True, "bounds": [28, 100, 70, 142], "tone": "light"},
    ],
}


# ── SAFINUM SANDBOX : les 6 écrans complets (Web & Mobile, FR & Ewondo) ────

SAFINUM_HOME_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "h_bal_lbl", "tag": "span", "text": "Itan ineu", "clickable": False, "bounds": [420, 210, 520, 230], "tone": "dark"},
        {"node_id": "h_bal", "tag": "span", "text": "102 096 FCFA", "clickable": False, "bounds": [420, 240, 620, 290], "tone": "dark"},
        {"node_id": "h_q", "tag": "h3", "text": "Za dzam wa yi bo?", "clickable": False, "bounds": [680, 210, 860, 235], "tone": "light"},
        {"node_id": "h_tr", "tag": "button", "text": "Lomo moni", "clickable": True, "bounds": [680, 260, 820, 310], "tone": "light"},
        {"node_id": "h_bill", "tag": "button", "text": "Yaan mfie ai kalara", "clickable": True, "bounds": [840, 260, 1020, 310], "tone": "light"},
        {"node_id": "h_air", "tag": "button", "text": "Kus kredi telefon", "clickable": True, "bounds": [680, 330, 820, 380], "tone": "light"},
        {"node_id": "h_hist", "tag": "button", "text": "Itang mvet yam", "clickable": True, "bounds": [840, 330, 1020, 380], "tone": "light"},
        {"node_id": "h_wog", "tag": "button", "text": "Wog", "clickable": True, "bounds": [980, 120, 1050, 155], "tone": "light"},
    ],
}

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

SAFINUM_PAY_BILL_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "pb_h", "tag": "h2", "text": "Yaan", "clickable": False, "bounds": [540, 210, 640, 240], "tone": "light"},
        {"node_id": "pb_tab1", "tag": "button", "text": "Kalara", "clickable": True, "bounds": [540, 260, 630, 295], "tone": "light"},
        {"node_id": "pb_tab2", "tag": "button", "text": "Kredi", "clickable": True, "bounds": [645, 260, 735, 295], "tone": "light"},
        {"node_id": "pb_srv", "tag": "label", "text": "Tob isae", "clickable": False, "bounds": [540, 320, 680, 345], "tone": "light"},
        {"node_id": "pb_eneo", "tag": "button", "text": "ENEO", "clickable": True, "bounds": [540, 360, 640, 400], "tone": "light"},
        {"node_id": "pb_amt", "tag": "label", "text": "Itan", "clickable": False, "bounds": [540, 430, 620, 455], "tone": "light"},
        {"node_id": "pb_go", "tag": "button", "text": "Kele obusu", "clickable": True, "bounds": [700, 520, 820, 560], "tone": "light"},
    ],
}

SAFINUM_PAY_AIRTIME_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "pa_tab1", "tag": "button", "text": "Kalara", "clickable": True, "bounds": [540, 260, 630, 295], "tone": "light"},
        {"node_id": "pa_tab2", "tag": "button", "text": "Kredi", "clickable": True, "bounds": [645, 260, 735, 295], "tone": "light"},
        {"node_id": "pa_phone", "tag": "label", "text": "Nombo ya lomo kredi", "clickable": False, "bounds": [540, 320, 760, 345], "tone": "light"},
        {"node_id": "pa_op", "tag": "span", "text": "Nsaa a yenban: MTN", "clickable": False, "bounds": [540, 390, 740, 415], "tone": "light"},
        {"node_id": "pa_amt", "tag": "label", "text": "Itan", "clickable": False, "bounds": [540, 430, 620, 455], "tone": "light"},
        {"node_id": "pa_go", "tag": "button", "text": "Kele obusu", "clickable": True, "bounds": [700, 520, 820, 560], "tone": "light"},
    ],
}

SAFINUM_REVIEW_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "rv_t", "tag": "h2", "text": "Fombo ossussua eneu wa yemban", "clickable": False, "bounds": [540, 210, 860, 240], "tone": "light"},
        {"node_id": "rv_warn", "tag": "p", "text": "Moni a ke di a te wa yemban.", "clickable": False, "bounds": [540, 260, 860, 285], "tone": "light"},
        {"node_id": "rv_edit", "tag": "button", "text": "Tyende", "clickable": True, "bounds": [540, 520, 640, 560], "tone": "light"},
        {"node_id": "rv_cancel", "tag": "button", "text": "Vaa", "clickable": True, "bounds": [650, 520, 730, 560], "tone": "light"},
        {"node_id": "rv_ok", "tag": "button", "text": "Yemban", "clickable": True, "bounds": [740, 520, 860, 560], "tone": "light"},
    ],
}

SAFINUM_RECEIPT_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "rc_ok", "tag": "h2", "text": "Mvet o boban mben", "clickable": False, "bounds": [540, 210, 820, 240], "tone": "light"},
        {"node_id": "rc_ref", "tag": "span", "text": "Nombo ndem", "clickable": False, "bounds": [540, 310, 680, 335], "tone": "light"},
        {"node_id": "rc_refv", "tag": "span", "text": "TX-98412", "clickable": False, "bounds": [700, 310, 820, 335], "tone": "light"},
        {"node_id": "rc_bal", "tag": "span", "text": "Itan mfefe", "clickable": False, "bounds": [540, 360, 680, 385], "tone": "light"},
        {"node_id": "rc_balv", "tag": "span", "text": "101 596 FCFA", "clickable": False, "bounds": [700, 360, 840, 385], "tone": "light"},
    ],
}

SAFINUM_HISTORY_CTX = {
    "type": "screen_context",
    "channel": "web",
    "page": {"url": "https://safinum.cm/sandbox/channel/web", "title": "Safinum Banque démo"},
    "screen_hint": "home",
    "nodes": [
        {"node_id": "hi_t", "tag": "h2", "text": "Itang mvet", "clickable": False, "bounds": [540, 210, 720, 240], "tone": "light"},
        {"node_id": "hi_all", "tag": "button", "text": "Mese", "clickable": True, "bounds": [540, 260, 610, 295], "tone": "light"},
        {"node_id": "hi_in", "tag": "button", "text": "Bi bi", "clickable": True, "bounds": [620, 260, 690, 295], "tone": "light"},
        {"node_id": "hi_out", "tag": "button", "text": "Bi lom", "clickable": True, "bounds": [700, 260, 780, 295], "tone": "light"},
    ],
}


def test_header_guard_never_frames_page_titles():
    nodes = [
        ScreenNode(node_id="title_android", tag="span", text="Send Money", clickable=False, bounds=[126, 98, 344, 146]),
        ScreenNode(node_id="title_web", tag="h2", text="Envoyer de l'argent", clickable=False, bounds=[540, 220, 740, 250]),
    ]
    assert AppPlaybookStore.find_matching_node(nodes, ["send"], prefer_button=True) is None
    assert AppPlaybookStore.find_matching_node(nodes, ["envoyer de l'argent"], prefer_button=True) is None


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

    # 2. "Comment envoyer de l'argent ?" sur Wave Home -> cadre directement `Send` (n_01)
    r_send = client.post("/answer", json={"transcript": "Comment envoyer de l'argent ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert r_send.status_code == 200
    acts_send = r_send.json()["actions"]
    spoken_send = " ".join(a["action"].get("text", "") for a in acts_send if a["action"]["t"] == "speak").lower()
    assert "incapable" not in spoken_send and "hors contexte" not in spoken_send
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_01" for a in acts_send)

    # 3. Scénarios débutants Wave Home
    r_qr = client.post("/answer", json={"transcript": "À quoi sert le QR code ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert "scanner" in " ".join(a["action"].get("text", "") for a in r_qr.json()["actions"] if a["action"]["t"] == "speak").lower()

    r_vault = client.post("/answer", json={"transcript": "C'est quoi Vault ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_03" for a in r_vault.json()["actions"])

    r_hide = client.post("/answer", json={"transcript": "Comment cacher mon solde ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    assert any(a["action"]["t"] == "circle" and a["action"]["target"]["node_id"] == "n_10" for a in r_hide.json()["actions"])

    r_guide = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_REAL_CTX})
    spoken_guide = " ".join(a["action"].get("text", "") for a in r_guide.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "wave" in spoken_guide and "qr code" in spoken_guide


def test_wave_send_money_subscreen_never_frames_header_and_guides_user():
    # Régression exacte de la capture utilisateur : DÉJÀ sur Wave `Send Money`, demande "Je veux envoyer de l'argent"
    r = client.post("/answer", json={"transcript": "Je veux envoyer de l'argent", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    assert r.status_code == 200
    acts = r.json()["actions"]
    spoken = " ".join(a["action"].get("text", "") for a in acts if a["action"]["t"] == "speak").lower()
    assert "déjà sur l'écran d'envoi" in spoken
    assert "enter a new number" in spoken and "scan to send" in spoken
    target_ids = [a["action"]["target"]["node_id"] for a in acts if a["action"].get("target")]
    assert "w_title" not in target_ids  # JAMAIS encadrer le titre "Send Money" !
    assert "w_new" in target_ids and "w_scan" in target_ids

    # "Je dois faire quoi ici ?" sur Send Money
    r_g = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    acts_g = r_g.json()["actions"]
    assert all((a["action"].get("target") or {}).get("node_id") != "w_title" for a in acts_g)
    assert any((a["action"].get("target") or {}).get("node_id") == "w_new" for a in acts_g)

    # "Comment envoyer à un nouveau numéro ?" -> cadre `Enter a new number`
    r_new = client.post("/answer", json={"transcript": "Comment envoyer à un nouveau numéro pas dans mes contacts ?", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "w_new" for a in r_new.json()["actions"])

    # "Comment scanner un QR code ?" -> cadre `Scan to send`
    r_sc = client.post("/answer", json={"transcript": "Comment scanner un QR code ?", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "w_scan" for a in r_sc.json()["actions"])

    # "Comment revenir en arrière ?" -> cercle sur `Back`
    r_bk = client.post("/answer", json={"transcript": "Comment revenir en arrière ?", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    assert any(a["action"]["t"] == "circle" and a["action"]["target"]["node_id"] == "w_back" for a in r_bk.json()["actions"])

    # "Où sont mes contacts ?" -> parle à la 2e personne ("Tes contacts", JAMAIS "Mes contacts") + surligne Contacts
    r_ct = client.post("/answer", json={"transcript": "Où sont mes contacts ?", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
    spoken_ct = " ".join(a["action"].get("text", "") for a in r_ct.json()["actions"] if a["action"]["t"] == "speak")
    assert "tes contacts" in spoken_ct.lower() and "mes contacts" not in spoken_ct.lower()
    assert any(a["action"]["target"]["node_id"] == "w_contacts" for a in r_ct.json()["actions"] if a["action"].get("target"))

    # Guidage inter-écrans depuis Wave Send Money : "Quelles sont mes dernières opérations ?" & "Quel est mon solde ?" -> JAMAIS Hors contexte !
    for q_nav in ("Quelles sont mes dernières opérations ?", "C'est quoi mon solde ?"):
        r_nav = client.post("/answer", json={"transcript": q_nav, "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX})
        spoken_nav = " ".join(a["action"].get("text", "") for a in r_nav.json()["actions"] if a["action"]["t"] == "speak").lower()
        assert "incapable" not in spoken_nav and "hors contexte" not in spoken_nav
        assert "accueil" in spoken_nav
        assert any(a["action"]["t"] == "circle" and a["action"]["target"]["node_id"] == "w_back" for a in r_nav.json()["actions"])


def test_second_person_normalizer_and_safinum_cross_screen_guidance(monkeypatch):
    # 1. Même si le petit LLM 1.5B répond à la 1re personne ("Mes contacts sont...", "Mon solde est..."), le harnais corrige en "Tes / Ton"
    monkeypatch.setattr(
        "app.llm.requests.post",
        lambda *a, **kw: _FakeResp({
            "spoken": "Mes contacts sont listés ici et mon solde reste disponible dans « Mes opérations ».",
            "title": "Contacts",
            "rows": [],
            "targets": [],
        }),
    )
    r_p2 = client.post(
        "/answer",
        json={"transcript": "Parle-moi de Djunette ici", "lang_hint": "fr", "context": WAVE_SEND_MONEY_CTX},
    )
    spoken_p2 = " ".join(a["action"].get("text", "") for a in r_p2.json()["actions"] if a["action"]["t"] == "speak")
    assert "Tes contacts" in spoken_p2 and "ton solde" in spoken_p2.lower()
    assert "« Mes opérations »" in spoken_p2  # Libellé d'UI entre guillemets préservé !

    # 2. Régression exacte capture SAFINUM Mobile `/transfer` : "Quelles sont mes dernières opérations ?" -> guide vers Historique (JAMAIS Hors contexte !)
    transfer_with_nav = dict(SAFINUM_TRANSFER_CTX)
    transfer_with_nav["nodes"] = list(SAFINUM_TRANSFER_CTX["nodes"]) + [
        {"node_id": "nav_home", "tag": "button", "text": "Accueil", "clickable": True, "bounds": [420, 740, 490, 780], "tone": "light"},
        {"node_id": "nav_hist", "tag": "button", "text": "Historique", "clickable": True, "bounds": [640, 740, 720, 780], "tone": "light"},
        {"node_id": "nav_pay", "tag": "button", "text": "Payer", "clickable": True, "bounds": [560, 740, 630, 780], "tone": "light"},
    ]
    r_hist = client.post("/answer", json={"transcript": "Quelles sont mes dernières opérations ?", "lang_hint": "fr", "context": transfer_with_nav})
    body_hist = r_hist.json()
    acts_hist = body_hist["actions"]
    spoken_hist = " ".join(a["action"].get("text", "") for a in acts_hist if a["action"]["t"] == "speak").lower()
    assert "incapable" not in spoken_hist and "hors contexte" not in spoken_hist
    assert "historique" in spoken_hist
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "nav_hist" for a in acts_hist)
    assert body_hist.get("follow_up") is not None
    assert "history" in body_hist["follow_up"]["target_screens"]
    assert body_hist["follow_up"]["question"] == "Quelles sont mes dernières opérations ?"

    r_bal = client.post("/answer", json={"transcript": "Quel est mon solde ?", "lang_hint": "fr", "context": transfer_with_nav})
    body_bal = r_bal.json()
    acts_bal = body_bal["actions"]
    spoken_bal = " ".join(a["action"].get("text", "") for a in acts_bal if a["action"]["t"] == "speak").lower()
    assert "incapable" not in spoken_bal and "accueil" in spoken_bal
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "nav_home" for a in acts_bal)
    assert body_bal.get("follow_up") is not None
    assert body_bal["follow_up"]["target_screens"] == ["home"]
    assert any("solde" in c or "itan ineu" in c for c in body_bal["follow_up"]["target_cues"])

    # Wave Send Money -> demande de solde renvoie aussi un follow_up vers l'accueil Wave ET entoure "Navigate up"
    wave_nav_up = dict(WAVE_SEND_MONEY_CTX)
    wave_nav_up["nodes"] = [
        {"node_id": "w_nav", "tag": "button", "text": "", "content_desc": "Navigate up", "clickable": True, "bounds": [28, 96, 76, 144], "tone": "light"},
        *[n for n in WAVE_SEND_MONEY_CTX["nodes"] if n["node_id"] != "w_back"],
    ]
    r_wave_bal = client.post("/answer", json={"transcript": "C'est quoi mon solde ?", "lang_hint": "fr", "context": wave_nav_up})
    body_wb = r_wave_bal.json()
    assert body_wb.get("follow_up") is not None
    assert body_wb["follow_up"]["target_screens"] == ["home"]
    assert "hide balance" in body_wb["follow_up"]["target_cues"]
    assert any(a["action"]["t"] == "circle" and a["action"]["target"]["node_id"] == "w_nav" for a in body_wb["actions"])

    # Régression exacte multi-page Historique : /history avec Facture ENEO + Crédit MTN ne doit JAMAIS être classé `pay` ni reboucler !
    history_with_bill_and_airtime = {
        "type": "screen_context",
        "channel": "mobile",
        "page": {"url": "https://safinum.cm/sandbox/channel/mobile", "title": "Safinum Banque démo"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "ht", "tag": "h2", "text": "Historique", "clickable": False, "bounds": [430, 190, 560, 220], "tone": "light"},
            {"node_id": "hf1", "tag": "button", "text": "Tout", "clickable": True, "bounds": [430, 235, 480, 265], "tone": "light"},
            {"node_id": "hf2", "tag": "button", "text": "Entrants", "clickable": True, "bounds": [490, 235, 565, 265], "tone": "light"},
            {"node_id": "hf3", "tag": "button", "text": "Sortants", "clickable": True, "bounds": [575, 235, 650, 265], "tone": "light"},
            {"node_id": "tx1_l", "tag": "span", "text": "Facture ENEO", "clickable": False, "bounds": [430, 310, 560, 335], "tone": "light"},
            {"node_id": "tx1_a", "tag": "span", "text": "-600 FCFA", "clickable": False, "bounds": [620, 310, 720, 335], "tone": "light"},
            {"node_id": "tx2_l", "tag": "span", "text": "Crédit MTN", "clickable": False, "bounds": [430, 370, 560, 395], "tone": "light"},
            {"node_id": "tx2_a", "tag": "span", "text": "-1 000 FCFA", "clickable": False, "bounds": [610, 370, 720, 395], "tone": "light"},
            {"node_id": "nav_h", "tag": "button", "text": "Historique", "clickable": True, "bounds": [640, 760, 720, 800], "tone": "light"},
        ],
    }
    r_hist_arrived = client.post(
        "/answer",
        json={"transcript": "Quelles sont mes dernières opérations ?", "lang_hint": "fr", "context": history_with_bill_and_airtime},
    )
    body_ha = r_hist_arrived.json()
    assert body_ha.get("follow_up") is None  # JAMAIS reboucler vers Historique quand on y est déjà !
    spoken_ha = " ".join(a["action"].get("text", "") for a in body_ha["actions"] if a["action"]["t"] == "speak")
    assert "appuie sur l'onglet historique" not in spoken_ha.lower()
    assert "facture eneo" in spoken_ha.lower() and "600 fcfa" in spoken_ha.lower()
    assert "crédit mtn" in spoken_ha.lower() or "credit mtn" in spoken_ha.lower()

    # Vérifie le nouveau lexique Douala validé ("Misongi", "Moni mu mingeyè", "Moni mu mabusè", "Sawa la ENEO")
    history_douala = {
        "type": "screen_context",
        "channel": "mobile",
        "page": {"url": "https://safinum.cm/sandbox/channel/mobile", "title": "Safinum Banque démo"},
        "screen_hint": "home",
        "nodes": [
            {"node_id": "d_t", "tag": "h2", "text": "Misongi", "clickable": False, "bounds": [430, 190, 560, 220], "tone": "light"},
            {"node_id": "d_f1", "tag": "button", "text": "Misongi mèsè", "clickable": True, "bounds": [430, 235, 510, 265], "tone": "light"},
            {"node_id": "d_f2", "tag": "button", "text": "Moni mu mingeyè", "clickable": True, "bounds": [515, 235, 620, 265], "tone": "light"},
            {"node_id": "d_f3", "tag": "button", "text": "Moni mu mabusè", "clickable": True, "bounds": [625, 235, 730, 265], "tone": "light"},
            {"node_id": "d_tx1", "tag": "span", "text": "Sawa la ENEO", "clickable": False, "bounds": [430, 310, 560, 335], "tone": "light"},
            {"node_id": "d_tx1a", "tag": "span", "text": "-600 FCFA", "clickable": False, "bounds": [620, 310, 720, 335], "tone": "light"},
        ],
    }
    r_hd = client.post("/answer", json={"transcript": "Quelles sont mes dernières opérations ?", "lang_hint": "fr", "context": history_douala})
    body_hd = r_hd.json()
    assert body_hd.get("follow_up") is None
    spoken_hd = " ".join(a["action"].get("text", "") for a in body_hd["actions"] if a["action"]["t"] == "speak")
    assert "600 fcfa" in spoken_hd.lower()

    r_safe = client.post("/answer", json={"transcript": "Est-ce débité tout de suite si j'appuie sur Continuer ?", "lang_hint": "fr", "context": transfer_with_nav})
    spoken_safe = " ".join(a["action"].get("text", "") for a in r_safe.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "récapitulatif" in spoken_safe and "confirmer" in spoken_safe


def test_wave_other_subscreens_amount_vault_card_qr():
    # Send Amount
    r_amt = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_SEND_AMOUNT_CTX})
    spoken_amt = " ".join(a["action"].get("text", "") for a in r_amt.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "send amount" in spoken_amt and "frais" in spoken_amt

    # Vault
    r_v = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_VAULT_CTX})
    spoken_v = " ".join(a["action"].get("text", "") for a in r_v.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "coffre" in spoken_v

    # Fullscreen QR
    r_q = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": WAVE_CARD_QR_CTX})
    spoken_q = " ".join(a["action"].get("text", "") for a in r_q.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "qr code" in spoken_q


def test_safinum_all_six_screens_flows():
    # 1. HOME : "Je veux envoyer de l'argent" -> cadre `Lomo moni`
    r_h = client.post("/answer", json={"transcript": "Je veux envoyer de l'argent", "lang_hint": "fr", "context": SAFINUM_HOME_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "h_tr" for a in r_h.json()["actions"])

    # 2. TRANSFER : "Je veux envoyer de l'argent" (déjà dessus!) -> JAMAIS cadre sur h2 `n_01`, guide 1-2-3 !
    r_t_send = client.post("/answer", json={"transcript": "Je veux envoyer de l'argent", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    acts_ts = r_t_send.json()["actions"]
    spoken_ts = " ".join(a["action"].get("text", "") for a in acts_ts if a["action"]["t"] == "speak").lower()
    assert "déjà sur l'écran de transfert" in spoken_ts
    tids_ts = [a["action"]["target"]["node_id"] for a in acts_ts if a["action"].get("target")]
    assert "n_01" not in tids_ts
    assert "n_02" in tids_ts and "n_04" in tids_ts and "n_07" in tids_ts

    # 2b. TRANSFER : "Je dois faire quoi ici ?", plafond, liste contacts, annuler
    r_guide = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    spoken_g = " ".join(a["action"].get("text", "") for a in r_guide.json()["actions"] if a["action"]["t"] == "speak").lower()
    assert "blaise" not in spoken_g and "500 000" not in spoken_g
    assert "bénéficiaire" in spoken_g and "montant" in spoken_g and "continuer" in spoken_g

    r_lim = client.post("/answer", json={"transcript": "Je dois envoyer 500 000 FCFA ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    assert "plafond" in " ".join(a["action"].get("text", "") for a in r_lim.json()["actions"] if a["action"]["t"] == "speak").lower()

    r_list = client.post("/answer", json={"transcript": "C'est quoi la liste à droite avec Blaise Tchami ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    assert "contacts" in " ".join(a["action"].get("text", "") for a in r_list.json()["actions"] if a["action"]["t"] == "speak").lower()

    r_cancel = client.post("/answer", json={"transcript": "Comment annuler ?", "lang_hint": "fr", "context": SAFINUM_TRANSFER_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "n_06" for a in r_cancel.json()["actions"])

    # 3. PAY_BILL : guide + bascule vers onglet Crédit (`Kredi`)
    r_pb = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": SAFINUM_PAY_BILL_CTX})
    assert "facture" in " ".join(a["action"].get("text", "") for a in r_pb.json()["actions"] if a["action"]["t"] == "speak").lower()
    r_pb_sw = client.post("/answer", json={"transcript": "Je veux acheter du crédit", "lang_hint": "fr", "context": SAFINUM_PAY_BILL_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "pb_tab2" for a in r_pb_sw.json()["actions"])

    # 4. PAY_AIRTIME : guide + bascule vers onglet Facture (`Kalara`)
    r_pa = client.post("/answer", json={"transcript": "Je dois faire quoi ici ?", "lang_hint": "fr", "context": SAFINUM_PAY_AIRTIME_CTX})
    assert "crédit" in " ".join(a["action"].get("text", "") for a in r_pa.json()["actions"] if a["action"]["t"] == "speak").lower()
    r_pa_sw = client.post("/answer", json={"transcript": "Je veux payer une facture ENEO", "lang_hint": "fr", "context": SAFINUM_PAY_AIRTIME_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "pa_tab1" for a in r_pa_sw.json()["actions"])

    # 5. REVIEW : modifier (`Tyende`) et confirmer (`Yemban`)
    r_rv_ed = client.post("/answer", json={"transcript": "Comment modifier si je me suis trompé ?", "lang_hint": "fr", "context": SAFINUM_REVIEW_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "rv_edit" for a in r_rv_ed.json()["actions"])
    r_rv_ok = client.post("/answer", json={"transcript": "Comment confirmer ?", "lang_hint": "fr", "context": SAFINUM_REVIEW_CTX})
    assert any(a["action"]["t"] == "frame" and a["action"]["target"]["node_id"] == "rv_ok" for a in r_rv_ok.json()["actions"])

    # 6. RECEIPT : preuve / référence (`Nombo ndem`)
    r_rc = client.post("/answer", json={"transcript": "L'argent est bien parti ? Où est la preuve ?", "lang_hint": "fr", "context": SAFINUM_RECEIPT_CTX})
    assert any(a["action"]["target"]["node_id"] == "rc_ref" for a in r_rc.json()["actions"] if a["action"].get("target"))

    # 7. HISTORY : filtres (`Bi bi` / `Bi lom`)
    r_hi = client.post("/answer", json={"transcript": "Comment filtrer seulement les reçus ?", "lang_hint": "fr", "context": SAFINUM_HISTORY_CTX})
    tids_hi = [a["action"]["target"]["node_id"] for a in r_hi.json()["actions"] if a["action"].get("target")]
    assert "hi_in" in tids_hi and "hi_out" in tids_hi
