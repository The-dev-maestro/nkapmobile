"""Couche linguistique multicanale SAFINUM (Ewondo, Duala, Français, Anglais)."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.sandbox.gsm7 import fit_gsm7

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
ORTHOGRAPHY_STATE_FILE = TRANSLATIONS_DIR / ".orthography_mode"
SUPPORTED_LANGS = {"ewo", "dua", "en", "fr"}
ALLOWED_ORTHOGRAPHIES = {"aglc", "intuitive"}

_DICT_CACHE: dict[tuple[str, str], dict[str, str]] = {}
_UI_CACHE: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}


def get_orthography_mode() -> str:
    """Retourne le mode d'écriture actif ('aglc' ou 'intuitive')."""
    if ORTHOGRAPHY_STATE_FILE.exists():
        try:
            val = ORTHOGRAPHY_STATE_FILE.read_text(encoding="utf-8").strip().lower()
            if val in ALLOWED_ORTHOGRAPHIES:
                return val
        except OSError:
            pass
    env_val = str(os.getenv("NKAP_ORTHOGRAPHY", "")).strip().lower()
    if env_val in ALLOWED_ORTHOGRAPHIES:
        return env_val
    return "aglc"


def set_orthography_mode(mode: str) -> str:
    """Bascule le mode d'écriture ('aglc' ou 'intuitive') et vide les caches UI."""
    norm_mode = str(mode or "").strip().lower()
    if norm_mode not in ALLOWED_ORTHOGRAPHIES:
        raise ValueError(f"Mode d'orthographe invalide: {mode!r} (attendu: aglc | intuitive)")
    ORTHOGRAPHY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ORTHOGRAPHY_STATE_FILE.write_text(norm_mode + "\n", encoding="utf-8")
    _DICT_CACHE.clear()
    _UI_CACHE.clear()
    return norm_mode


def _norm(text: str | None) -> str:
    s = unicodedata.normalize("NFD", str(text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("ɛ", "e").replace("ɔ", "o").replace("ŋ", "n").replace("ə", "e").replace("ɓ", "b")
    return re.sub(r"\s+", " ", s).strip()


def load_dictionary(lang: str, mode: str | None = None) -> dict[str, str] | None:
    code = (lang or "").strip().lower()
    if code not in {"ewo", "dua", "en"}:
        return None
    active_mode = (mode or get_orthography_mode()).strip().lower()
    if active_mode not in ALLOWED_ORTHOGRAPHIES:
        active_mode = "aglc"
    cache_key = (code, active_mode)
    if cache_key in _DICT_CACHE:
        return _DICT_CACHE[cache_key]
    path = TRANSLATIONS_DIR / f"{code}_intuitive.json" if active_mode == "intuitive" else TRANSLATIONS_DIR / f"{code}.json"
    if not path.exists():
        path = TRANSLATIONS_DIR / f"{code}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    _DICT_CACHE[cache_key] = data
    return data


def _extract_placeholders(text: str) -> list[str]:
    return sorted(set(re.findall(r"\{[a-z_]+\}", str(text or ""))))


def _fit_max_chars(value: str, limit: int | None) -> str:
    if not limit or len(value) <= limit:
        return value
    # Si aucun placeholder dans la zone tronquée, raccourcit proprement
    candidate = value[:limit].rstrip()
    if _extract_placeholders(candidate) == _extract_placeholders(value):
        return candidate
    return value[:limit]


def translate_ui(payload: dict[str, Any]) -> dict[str, Any]:
    """Implémente le contrat officiel `ui_translation` (canaux mobile & web)."""
    requested = str(payload.get("language") or "fr").strip().lower()
    screen = str(payload.get("screen") or "unknown")
    source = payload.get("strings") or {}

    if requested == "fr" or requested not in {"ewo", "dua", "en"}:
        return {
            "language": "fr",
            "strings": {k: str((v or {}).get("text", "")) for k, v in source.items()},
        }

    active_mode = get_orthography_mode()
    cache_key = (requested, active_mode, screen, tuple(sorted(source.keys())))
    if cache_key in _UI_CACHE:
        return _UI_CACHE[cache_key]

    dictionary = load_dictionary(requested, mode=active_mode)
    if dictionary is None:
        return {
            "language": "fr",
            "strings": {k: str((v or {}).get("text", "")) for k, v in source.items()},
        }

    translated: dict[str, str] = {}
    for key, entry in source.items():
        entry_dict = entry if isinstance(entry, dict) else {"text": str(entry)}
        src_text = str(entry_dict.get("text") or "")
        max_chars = entry_dict.get("max_chars")
        val = dictionary.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        if _extract_placeholders(val) != _extract_placeholders(src_text):
            continue
        val = _fit_max_chars(val.strip(), int(max_chars) if max_chars else None)
        translated[key] = val

    result = {"language": requested, "strings": translated}
    if len(_UI_CACHE) < 128:
        _UI_CACHE[cache_key] = result
    return result


# ── Compréhension multilingue (Ewondo, Duala, Français, Anglais) ───────────

def _has_word(norm_text: str, phrases: tuple[str, ...]) -> bool:
    for p in phrases:
        if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", norm_text):
            return True
    return False


def detect_language_switch(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    lang_map = {
        "ewo": ("ewondo", "ewo"),
        "dua": ("duala", "douala", "dua"),
        "fr": ("francais", "french", "fr"),
        "en": ("anglais", "english", "en"),
    }
    # 1. Exact bare language name or code (ex: "ewondo", "duala", "fr", "en")
    for code, tokens in lang_map.items():
        if n in tokens:
            return code

    # 2. Preposition + explicit language name (jamais "en <mot quelconque>" -> "en" !)
    prep_match = re.search(
        r"\b(?:en|in|to)\s+(ewondo|ewo|duala|douala|dua|francais|french|anglais|english)\b",
        n,
    )
    if prep_match:
        tok = prep_match.group(1)
        for code, tokens in lang_map.items():
            if tok in tokens:
                return code

    # 3. Explicit language-switch trigger + language token
    switch_triggers = (
        "langue", "language", "parle", "parler", "passe en", "passer en",
        "switch", "change to", "kobo", "nkobo", "bwele", "tyende nkobo",
        "tukwa bwambo", "wengisane eyeme", "wenginane bwambo", "eyeme", "bwambo",
    )
    if _has_word(n, switch_triggers):
        for code, tokens in lang_map.items():
            for tok in tokens:
                # Évite que la préposition française "en" dans "passer en fulfulde" bascule en anglais
                if tok == "en" and re.search(r"\b(?:passe|passer|parle|parler)\s+en\b", n):
                    continue
                if re.search(rf"\b{re.escape(tok)}\b", n):
                    return code
    return None


def detect_term_question(text: str, *, allow_bare: bool = True) -> str | None:
    n = _norm(text)
    if not n:
        return None
    asks_def = "?" in str(text or "") or _has_word(
        n,
        (
            "c'est quoi", "cest quoi", "veut dire", "signifie", "explique",
            "definition", "what is", "za ne", "nje ne", "e ne dze", "e ne za",
            "terme", "mot", "sens", "teleya mba",
        ),
    )
    # Ne jamais détourner une commande d'action (ex: "modifier beneficiaire Franck", "envoyer a Paul Ndongo")
    has_action_verb = _has_word(
        n,
        (
            "modifier", "modifie", "corriger", "corrige", "changer", "change",
            "envoyer", "envoie", "transferer", "transfert", "send", "lomo", "lom",
            "loma", "payer", "pay", "annuler", "confirmer", "tyende", "tukwa",
        ),
    )
    bare_ok = allow_bare and not has_action_verb and len(n.split()) <= 2

    if _has_word(n, ("microfinance", "micro finance", "micro-finance")):
        return "microfinance" if (asks_def or bare_ok) else None
    if _has_word(n, ("plafond", "limite", "limit", "nkuk", "ndongo", "jasame", "mwasame")):
        return "limit" if (asks_def or bare_ok) else None
    if _has_word(n, ("beneficiaire", "destinataire", "beneficiary", "mukusa", "mukusedi", "mukuse", "mutombwedi", "mutombwanedi")):
        return "beneficiary" if (asks_def or bare_ok) else None
    if asks_def and _has_word(n, ("frais", "fee", "mbug", "mabala", "musen", "mususedi", "commission", "tarif")):
        return "fee"
    if asks_def and _has_word(n, ("epargne", "epargner", "saving", "savings")):
        return "epargne"
    if asks_def and _has_word(n, ("credit", "pret", "emprunt", "loan", "microcredit")):
        return "credit"
    if asks_def and _has_word(n, ("tontine", "njangi")):
        return "tontine"
    if asks_def and _has_word(n, ("mobile money", "momo", "orange money", "wallet")):
        return "mobile_money"
    if asks_def and _has_word(n, ("ussd", "code court")):
        return "ussd"
    if asks_def and _has_word(n, ("code pin", "code secret", "pin")):
        return "pin"
    return None


def parse_amount(text: str) -> int | None:
    # Évite de confondre un numéro camerounais (6XXXXXXXX, 6XX XX XX XX ou +237 6XX...) avec un montant
    cleaned = re.sub(r"(?<!\d)(?:\+?237[\s.-]?)?6(?:[\s.-]?\d){8}(?!\d)", " ", text or "")
    matches = re.findall(r"\b\d[\d\s.]{0,9}\d\b|\b\d+\b", cleaned)
    for m in matches:
        digits = re.sub(r"\D+", "", m)
        if digits and 1 <= len(digits) <= 7:
            val = int(digits)
            if val > 0:
                return val
    return None


def parse_phone(text: str) -> str | None:
    compact = re.sub(r"[\s.-]+", "", text or "")
    m = re.search(r"(?<!\d)(?:\+?237)?(6\d{8})(?!\d)", compact)
    if m:
        return "237" + m.group(1)
    return None


def detect_biller(text: str) -> str | None:
    n = _norm(text)
    if _has_word(n, ("eneo", "electricite", "courant", "lumiere", "mfie", "weya")):
        return "ENEO"
    if _has_word(n, ("camwater", "eau", "mendim", "medzim", "madiba", "water")):
        return "CAMWATER"
    if _has_word(n, ("canal", "canal+", "tele", "tv")):
        return "CANAL"
    if _has_word(n, ("camtel", "internet", "wifi")):
        return "CAMTEL"
    return None


def detect_intent_keyword(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    # Priorité CORRECTION avant CONFIRM/CANCEL (ex: "non finalement 5000", "oui modifier 10000")
    if _has_word(n, ("corriger", "corrige", "modifier", "modifie", "changer", "change", "finalement", "plutot", "tyende", "tsenegue", "tukwa", "wengisane", "engele", "na wondi", "edit")):
        return "CORRECTION"
    if _has_word(n, ("confirmer", "confirme", "confirm", "oui", "valider", "valide", "ok", "yes", "yemban", "yi wa yebeu", "yebeu", "yeba'ane", "yebaane", "bamse", "mbamse", "na kasi", "ne medi")):
        return "CONFIRM"
    if _has_word(n, ("annuler", "annule", "non", "stop", "cancel", "vaa", "dimi", "a tyam", "tyam", "buka", "esele", "essele", "a bangi", "kem")):
        return "CANCEL"
    if _has_word(n, ("frais", "combien coute", "cout", "tarif", "fee", "fees", "mbug", "be frais", "mabala", "musen", "mususedi", "busise", "jombwa mbolo")):
        return "FEE_INQUIRY"
    if _has_word(n, ("historique", "dernieres operations", "transactions", "operations", "history", "itang", "ndouang", "me tang", "bebolo", "misongi", "misondi", "miango")):
        return "TRANSACTION_HISTORY"
    if _has_word(n, ("credit", "airtime", "recharge", "recharger", "unites", "kredi", "ikola", "wa couss ikola", "ebale", "djanda la mudi", "djanta musinga", "musinga", "londe la beboledi")):
        return "AIRTIME_PURCHASE"
    if _has_word(n, ("facture", "factures", "bill", "bills", "eneo", "camwater", "canal", "camtel", "kalara", "kalati", "yaana facture", "sawa", "saweya", "musawedi", "na pula wasa", "dipapa la")):
        return "BILL_PAYMENT"
    if _has_word(n, ("retrait", "retirer", "withdraw", "withdrawal", "gab", "atm", "nong moni", "vaagui", "busa moni", "kusa la moni", "sumua")):
        return "WITHDRAWAL"
    if _has_word(n, ("envoyer", "envoie", "transfert", "transferer", "transfer", "send", "lomo", "lom", "loma", "lomea", "tombise", "na ni tombele")):
        return "TRANSFER"
    if _has_word(n, ("solde", "combien j'ai", "combien il me reste", "mon argent", "balance", "itan", "ou beleu", "nden", "moni ma pene", "moni ma dia", "ekotedi", "nje e peti", "moni mu peti", "epetele", "nje ye etom yam", "edia", "bongo bene")):
        return "BALANCE_INQUIRY"
    return None


# ── Templates USSD/SMS localisés (garantis GSM-7 <= 182 car.) ──────────────

PHRASES: dict[str, dict[str, str]] = {
    "menu": {
        "ewo": "Safinum (Ewondo):\n1. Itan ineu a nkwap\n2. Lomo moni\n3. Be frais\n4. Ndouang\n5. Ikola\n6. Yaana facture\n7. Aide termes",
        "dua": "Idiba bwam! Safinum (Duala):\n1. Edia\n2. Loma moni\n3. Mususedi\n4. Miango\n5. Ebale\n6. Sawa\n7. Jongwane",
        "fr": "Safinum:\n1. Mon solde\n2. Transfert\n3. Frais\n4. Historique\n5. Credit\n6. Facture\n7. Termes",
        "en": "Safinum:\n1. Balance\n2. Transfer\n3. Fees\n4. History\n5. Airtime\n6. Bills\n7. Terms",
    },
    "balance": {
        "ewo": "Ou beleu {balance} a nkwap ({phone}).",
        "dua": "Moni mu diya ({phone}): {balance}.",
        "fr": "Votre solde ({phone}) est de {balance}.",
        "en": "Your balance ({phone}) is {balance}.",
    },
    "ask_transfer_to": {
        "ewo": "Nomba nkwal ngueu ki dzoe doue:",
        "dua": "Dina la mutombwedi / number:",
        "fr": "Nom ou numero du beneficiaire:",
        "en": "Beneficiary name or phone number:",
    },
    "ask_amount": {
        "ewo": "Tang moni (FCFA):",
        "dua": "Moni o maloma no (FCFA):",
        "fr": "Montant en FCFA:",
        "en": "Amount in FCFA:",
    },
    "ask_fee_amount": {
        "ewo": "Montant pour calculer les frais (FCFA):",
        "dua": "Montant pour calculer Mususedi (FCFA):",
        "fr": "Montant pour calculer les frais (FCFA):",
        "en": "Amount to check fees (FCFA):",
    },
    "fee_answer": {
        "ewo": "Lomo {amount}: be frais {fee}, total {total}.",
        "dua": "Loma {amount}: mususedi {fee}, musongi mu londi {total}.",
        "fr": "Envoi {amount}: frais {fee}, total {total}.",
        "en": "Send {amount}: fee {fee}, total {total}.",
    },
    "ambiguous_benef": {
        "ewo": "Plusieurs beneficiaires trouves. Choisissez:\n{choices}",
        "dua": "Moto nu pepe a ben di dina. Poso:\n{choices}",
        "fr": "Plusieurs beneficiaires trouves. Choisissez:\n{choices}",
        "en": "Multiple beneficiaries found. Pick one:\n{choices}",
    },
    "confirm_transfer": {
        "ewo": "Lomo {amount} -> {to}. Be frais {fee}, total {total}.\n1. Yi wa yebeu\n2. Dimi\n3. Modifier montant\n4. Modifier destinataire",
        "dua": "Loma {amount} o dina la {to}. Mususedi {fee}, total {total}.\n1. Bamse\n2. Sumua\n3. Tukwa musongi\n4. Tukwa mukusedi",
        "fr": "Envoi {amount} a {to}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier montant\n4. Modifier destinataire",
        "en": "Send {amount} to {to}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit amount\n4. Edit recipient",
    },
    "confirm_airtime": {
        "ewo": "Ikola {operator} {amount} -> {to}. Be frais {fee}, total {total}.\n1. Yi wa yebeu\n2. Dimi\n3. Modifier montant",
        "dua": "Ebale {operator} {amount} -> {to}. Mususedi {fee}, total {total}.\n1. Bamse\n2. Sumua\n3. Tukwa musongi",
        "fr": "Credit {operator} {amount} au {to}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier montant",
        "en": "{operator} airtime {amount} to {to}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit amount",
    },
    "confirm_bill": {
        "ewo": "Facture {biller} {amount}. Be frais {fee}, total {total}.\n1. Yi wa yebeu\n2. Dimi\n3. Modifier montant",
        "dua": "Sawa {biller} {amount}. Mususedi {fee}, total {total}.\n1. Bamse\n2. Sumua\n3. Tukwa musongi",
        "fr": "Facture {biller} {amount}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier montant",
        "en": "{biller} bill {amount}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit amount",
    },
    "confirm_withdrawal": {
        "ewo": "Retrait GAB {amount}. Be frais {fee}, total {total}.\n1. Yi wa yebeu\n2. Dimi\n3. Modifier montant",
        "dua": "Sumua GAB {amount}. Mususedi {fee}, total {total}.\n1. Bamse\n2. Sumua\n3. Tukwa musongi",
        "fr": "Retrait GAB {amount}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier montant",
        "en": "ATM withdrawal {amount}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit amount",
    },
    "confirmed": {
        "ewo": "Adzo a loren mbeung! {amount} -> {to}. Ref {ref}.",
        "dua": "Di tombi bwam! {amount} o dina la {to}. Epasi {ref}.",
        "fr": "Operation confirmee! {amount} pour {to}. Ref {ref}.",
        "en": "Confirmed! {amount} for {to}. Ref {ref}.",
    },
    "cancelled": {
        "ewo": "Operation annulee (Dimi). Aucun montant debite.",
        "dua": "Sumua. Moni mu si lomabe.",
        "fr": "Operation annulee. Aucun montant debite.",
        "en": "Transaction cancelled. Nothing debited.",
    },
    "ask_new_amount": {
        "ewo": "Entrez le nouveau montant (FCFA):",
        "dua": "Entrez le nouveau montant (FCFA):",
        "fr": "Entrez le nouveau montant (FCFA):",
        "en": "Enter the new amount (FCFA):",
    },
    "ask_new_beneficiary": {
        "ewo": "Nom ou numero du nouveau destinataire:",
        "dua": "Nom ou numero du nouveau destinataire:",
        "fr": "Nom ou numero du nouveau destinataire:",
        "en": "New recipient name or phone number:",
    },
    "ask_airtime_target": {
        "ewo": "Ikola:\n1. Mon numero\n2. Autre numero",
        "dua": "Ebale:\n1. Mon numero\n2. Autre numero",
        "fr": "Credit pour:\n1. Mon numero\n2. Autre numero",
        "en": "Airtime for:\n1. My number\n2. Another number",
    },
    "ask_airtime_phone": {
        "ewo": "Dzalga e numba wa loue (9 chiffres):",
        "dua": "Number ebelane (9 chiffres):",
        "fr": "Numero a recharger (9 chiffres):",
        "en": "Phone number to top up (9 digits):",
    },
    "ask_biller": {
        "ewo": "Facturier:\n1. ENEO (Mfie)\n2. CAMWATER (Medzim)\n3. CANAL (Tele)\n4. CAMTEL",
        "dua": "Poso:\n1. ENEO\n2. CAMWATER (Madiba)\n3. CANAL\n4. CAMTEL",
        "fr": "Facturier:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
        "en": "Biller:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
    },
    "ask_term": {
        "ewo": "Quel terme expliquer?\n1. Be frais (Frais)\n2. Plafond\n3. Beneficiaire",
        "dua": "Quel terme expliquer?\n1. Mususedi (Frais)\n2. Jasame (Plafond)\n3. Mukusedi (Beneficiaire)",
        "fr": "Quel terme expliquer?\n1. Frais\n2. Plafond\n3. Beneficiaire",
        "en": "Which term to explain?\n1. Fee\n2. Limit\n3. Beneficiary",
    },
    "term_fee": {
        "ewo": "Frais: petite somme retenue par la banque pour faire l'envoi (ex: 50 a 400 FCFA).",
        "dua": "Mususedi mwe nde moni bank mba ma nongo no (50 a 400 FCFA).",
        "fr": "Frais: petite somme retenue par la banque pour faire l'envoi (ex: 50 a 400 FCFA).",
        "en": "Fee: small amount the bank charges to process your transfer.",
    },
    "term_limit": {
        "ewo": "Plafond: montant maximum autorise par operation (500 000 FCFA).",
        "dua": "Jasame le nde musongi mwa moni o titi no na o loma nguedi po (500 000 FCFA).",
        "fr": "Plafond: montant maximum autorise par operation (500 000 FCFA).",
        "en": "Limit: maximum amount allowed in a single transaction (500 000 FCFA).",
    },
    "term_beneficiary": {
        "ewo": "Beneficiaire: la personne qui recoit votre argent. Verifiez toujours son numero.",
        "dua": "Mukusedi nde a makuse moni. Jombwa la dina na number mutombwedi.",
        "fr": "Beneficiaire: la personne qui recoit votre argent. Verifiez toujours son numero.",
        "en": "Beneficiary: the person receiving your money. Always check their number.",
    },
    "term_microfinance": {
        "ewo": "Microfinance: etablissement financier de proximite pour epargner, transferer et obtenir de petits prets.",
        "dua": "Microfinance: etablissement financier de proximite pour epargner, transferer et obtenir de petits prets.",
        "fr": "Microfinance: etablissement financier de proximite pour epargner, transferer et obtenir de petits prets.",
        "en": "Microfinance: local financial institution offering savings, transfers and small loans.",
    },
    "term_epargne": {
        "ewo": "Epargne: argent mis de cote en securite pour vos projets ou imprevus.",
        "dua": "Epargne: argent mis de cote en securite pour vos projets ou imprevus.",
        "fr": "Epargne: argent mis de cote en securite pour vos projets ou imprevus.",
        "en": "Savings: money set aside safely for future needs or emergencies.",
    },
    "term_credit": {
        "ewo": "Credit: somme pretee par une banque ou microfinance a rembourser progressivement.",
        "dua": "Credit: somme pretee par une banque ou microfinance a rembourser progressivement.",
        "fr": "Credit: somme pretee par une banque ou microfinance a rembourser progressivement.",
        "en": "Loan: money borrowed from a bank or microfinance and repaid over time.",
    },
    "term_tontine": {
        "ewo": "Tontine: epargne collective ou chaque membre cotise et recoit la cagnotte a tour de role.",
        "dua": "Tontine: epargne collective ou chaque membre cotise et recoit la cagnotte a tour de role.",
        "fr": "Tontine: epargne collective ou chaque membre cotise et recoit la cagnotte a tour de role.",
        "en": "Tontine: group savings circle where members contribute and take turns receiving the pot.",
    },
    "term_mobile_money": {
        "ewo": "Mobile Money: porte-monnaie lie a votre numero pour envoyer, payer et retirer.",
        "dua": "Mobile Money: porte-monnaie lie a votre numero pour envoyer, payer et retirer.",
        "fr": "Mobile Money: porte-monnaie lie a votre numero pour envoyer, payer et retirer.",
        "en": "Mobile Money: phone-linked wallet to send, pay bills and withdraw cash.",
    },
    "term_ussd": {
        "ewo": "USSD: menu bancaire par code court (*123#) qui marche sans internet.",
        "dua": "USSD: menu bancaire par code court (*123#) qui marche sans internet.",
        "fr": "USSD: menu bancaire par code court (*123#) qui marche sans internet.",
        "en": "USSD: short-code banking menu (*123#) that works without internet.",
    },
    "term_pin": {
        "ewo": "Code PIN: votre code secret personnel. Ne le partagez jamais, meme a un agent.",
        "dua": "Code PIN: votre code secret personnel. Ne le partagez jamais, meme a un agent.",
        "fr": "Code PIN: votre code secret personnel. Ne le partagez jamais, meme a un agent.",
        "en": "PIN code: your personal secret code. Never share it with anyone.",
    },
    "lang_switched": {
        "ewo": "Langue changee: Ewondo. {resume}",
        "dua": "Langue changee: Duala. {resume}",
        "fr": "Langue changee: Francais. {resume}",
        "en": "Language switched: English. {resume}",
    },
    "history_empty": {
        "ewo": "Tang zing idzikig boban.",
        "dua": "To lambo.",
        "fr": "Aucune operation recente.",
        "en": "No recent transactions.",
    },
    "invalid_amount": {
        "ewo": "Montant invalide. Tapez un nombre (ex: 5000):",
        "dua": "Number e si tem. Tapez un nombre (ex: 5000):",
        "fr": "Montant invalide. Tapez un nombre (ex: 5000):",
        "en": "Invalid amount. Enter a number (e.g. 5000):",
    },
    "invalid_phone": {
        "ewo": "Numero invalide. 9 chiffres, ex: 699000002",
        "dua": "Number e si tem. 9 chiffres, ex: 699000002",
        "fr": "Numero invalide. 9 chiffres, ex: 699000002",
        "en": "Invalid phone. 9 digits, e.g. 699000002",
    },
    "confirm_prompt_retry": {
        "ewo": "Tapez 1 (Yi wa yebeu), 2 (Dimi), 3 (Montant) ou 4 (Destinataire).",
        "dua": "Tapez 1 (Bamse), 2 (Sumua), 3 (Musongi) ou 4 (Mukusedi).",
        "fr": "Tapez 1 (Confirmer), 2 (Annuler), 3 (Montant) ou 4 (Destinataire).",
        "en": "Reply 1 (Confirm), 2 (Cancel), 3 (Amount) or 4 (Recipient).",
    },
    "atm_multiple": {
        "ewo": "Retrait GAB uniquement par multiples de 5 000 FCFA.",
        "dua": "Retrait GAB uniquement par multiples de 5 000 FCFA.",
        "fr": "Retrait GAB uniquement par multiples de 5 000 FCFA.",
        "en": "ATM withdrawals must be multiples of 5,000 FCFA.",
    },
    "err_INSUFFICIENT_FUNDS": {
        "ewo": "Solde insuffisant pour couvrir le montant et les frais. Essayez un montant plus petit.",
        "dua": "Moni mu si dongamene.",
        "fr": "Solde insuffisant pour couvrir le montant et les frais. Essayez un montant plus petit.",
        "en": "Insufficient balance for this amount and fee. Try a smaller amount.",
    },
    "err_LIMIT_EXCEEDED": {
        "ewo": "Montant superieur au plafond autorise (500 000 FCFA).",
        "dua": "Diwuse: moni mwasame (500 000 FCFA).",
        "fr": "Montant superieur au plafond autorise (500 000 FCFA).",
        "en": "Amount exceeds maximum limit (500,000 FCFA).",
    },
    "err_UNKNOWN_BENEFICIARY": {
        "ewo": "Beneficiaire introuvable. Verifiez le nom ou le numero.",
        "dua": "Si jene la mutombwanedi. Jombwa la dina na number mutombwedi.",
        "fr": "Beneficiaire introuvable. Verifiez le nom ou le numero.",
        "en": "Beneficiary not found. Check name or number.",
    },
    "err_UNKNOWN_ACCOUNT": {
        "ewo": "Compte introuvable.",
        "dua": "Compte introuvable.",
        "fr": "Compte introuvable.",
        "en": "Account not found.",
    },
    "err_UNKNOWN_BILLER": {
        "ewo": "Facturier inconnu. Choisissez ENEO, CAMWATER, CANAL ou CAMTEL.",
        "dua": "Diyo di titi. Poso ENEO, CAMWATER, CANAL / CAMTEL.",
        "fr": "Facturier inconnu. Choisissez ENEO, CAMWATER, CANAL ou CAMTEL.",
        "en": "Unknown biller. Choose ENEO, CAMWATER, CANAL or CAMTEL.",
    },
    "err_GENERIC": {
        "ewo": "Operation impossible pour le moment. Reessayez.",
        "dua": "Moni mu si lomabe. Kekise pete.",
        "fr": "Operation impossible pour le moment. Reessayez.",
        "en": "Operation unavailable right now. Please try again.",
    },
}


def resolve_lang(requested: str | None) -> str:
    code = str(requested or "").strip().lower()
    if code in SUPPORTED_LANGS:
        return code
    return "fr"


def render_phrase(key: str, lang: str | None, max_septets: int = 182, **kwargs: Any) -> tuple[str, str]:
    """Renvoie (texte GSM-7 <= max_septets, langue réellement déclarée)."""
    declared = resolve_lang(lang)
    table = PHRASES.get(key) or PHRASES["err_GENERIC"]
    tpl = table.get(declared) or table["fr"]
    if declared not in table:
        declared = "fr"
    try:
        raw = tpl.format(**kwargs)
    except Exception:
        raw = tpl
    return fit_gsm7(raw, max_septets=max_septets), declared
