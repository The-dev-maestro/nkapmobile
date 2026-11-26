"""Couche linguistique multicanale SAFINUM (Ewondo, Duala, Français, Anglais)."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.sandbox.gsm7 import fit_gsm7

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
SUPPORTED_LANGS = {"ewo", "dua", "en", "fr"}

_DICT_CACHE: dict[str, dict[str, str]] = {}
_UI_CACHE: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}


def _norm(text: str | None) -> str:
    s = unicodedata.normalize("NFD", str(text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("ɛ", "e").replace("ɔ", "o").replace("ŋ", "n").replace("ə", "e").replace("ɓ", "b")
    return re.sub(r"\s+", " ", s).strip()


def load_dictionary(lang: str) -> dict[str, str] | None:
    code = (lang or "").strip().lower()
    if code not in {"ewo", "dua", "en"}:
        return None
    if code in _DICT_CACHE:
        return _DICT_CACHE[code]
    path = TRANSLATIONS_DIR / f"{code}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    _DICT_CACHE[code] = data
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

    cache_key = (requested, screen, tuple(sorted(source.keys())))
    if cache_key in _UI_CACHE:
        return _UI_CACHE[cache_key]

    dictionary = load_dictionary(requested)
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

def detect_language_switch(text: str) -> str | None:
    n = _norm(text)
    switch_triggers = (
        "langue", "language", "parle", "parler", "passe en", "passer en",
        "switch", "change to", "kobo", "bato", "nkobo", "bwele",
    )
    lang_map = {
        "ewo": ("ewondo", "ewo"),
        "dua": ("duala", "douala", "dua"),
        "fr": ("francais", "french", "fr"),
        "en": ("anglais", "english", "en"),
    }
    has_trigger = any(t in n for t in switch_triggers)
    for code, tokens in lang_map.items():
        for tok in tokens:
            if n == tok or (has_trigger and re.search(rf"\b{tok}\b", n)):
                return code
    return None


def detect_term_question(text: str) -> str | None:
    n = _norm(text)
    asks_def = any(
        k in n
        for k in (
            "c'est quoi", "cest quoi", "veut dire", "signifie", "explique",
            "definition", "what is", "za ne", "nje ne", "terme", "mot", "sens",
        )
    )
    if "plafond" in n or "limite" in n or "limit" in n or "nkuk" in n or "ndongo" in n:
        return "limit" if (asks_def or len(n.split()) <= 3) else None
    if "beneficiaire" in n or "destinataire" in n or "beneficiary" in n or "mukusa" in n:
        return "beneficiary" if (asks_def or len(n.split()) <= 3) else None
    if asks_def and any(k in n for k in ("frais", "fee", "mbug", "mabala", "commission", "tarif")):
        return "fee"
    return None


def parse_amount(text: str) -> int | None:
    # Évite de confondre un numéro camerounais (6XXXXXXXX ou 2376XXXXXXXX) avec un montant
    cleaned = re.sub(r"\b(?:237)?6\d{8}\b", " ", text or "")
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
    m = re.search(r"(?:237)?(6\d{8})", compact)
    if m:
        return "237" + m.group(1)
    return None


def detect_biller(text: str) -> str | None:
    n = _norm(text)
    if any(k in n for k in ("eneo", "electricite", "courant", "lumiere", "mfie", "weya")):
        return "ENEO"
    if any(k in n for k in ("camwater", "eau", "mendim", "madiba", "water")):
        return "CAMWATER"
    if any(k in n for k in ("canal", "tele", "tv")):
        return "CANAL"
    if any(k in n for k in ("camtel", "internet", "wifi")):
        return "CAMTEL"
    return None


def detect_intent_keyword(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    if any(k in n for k in ("confirmer", "confirme", "oui", "valider", "ok", "yes", "yemban", "bamse")):
        return "CONFIRM"
    if any(k in n for k in ("annuler", "annule", "non", "stop", "cancel", "vaa", "buka")):
        return "CANCEL"
    if any(k in n for k in ("corriger", "corrige", "modifier", "modifie", "changer", "change", "finalement", "plutot", "tyende", "tukwa")):
        return "CORRECTION"
    if any(k in n for k in ("frais", "combien coute", "cout", "tarif", "fee", "mbug", "mabala")):
        return "FEE_INQUIRY"
    if any(k in n for k in ("historique", "dernieres operations", "transactions", "operations", "history", "itang", "bebolo")):
        return "TRANSACTION_HISTORY"
    if any(k in n for k in ("credit", "airtime", "recharge", "unites", "kredi")):
        return "AIRTIME_PURCHASE"
    if any(k in n for k in ("facture", "bill", "eneo", "camwater", "canal", "camtel", "kalara", "kalati")):
        return "BILL_PAYMENT"
    if any(k in n for k in ("retrait", "retirer", "withdraw", "gab", "atm", "nong moni", "busa moni")):
        return "WITHDRAWAL"
    if any(k in n for k in ("envoyer", "envoie", "transfert", "transferer", "send", "lomo", "lom", "loma")):
        return "TRANSFER"
    if any(k in n for k in ("solde", "combien j'ai", "combien il me reste", "mon argent", "balance", "itan", "nden", "moni ma pene", "moni ma dia")):
        return "BALANCE_INQUIRY"
    return None


# ── Templates USSD/SMS localisés (garantis GSM-7 <= 182 car.) ──────────────

PHRASES: dict[str, dict[str, str]] = {
    "menu": {
        "ewo": "Safinum (Ewondo):\n1. Itan ineu\n2. Lomo moni\n3. Mbug\n4. Itang mvet\n5. Kredi\n6. Kalara\n7. Aide termes",
        "dua": "Safinum (Duala):\n1. Moni ma pene\n2. Loma moni\n3. Mabala\n4. Bebolo\n5. Kredi\n6. Kalati\n7. Aide termes",
        "fr": "Safinum:\n1. Mon solde\n2. Transfert\n3. Frais\n4. Historique\n5. Credit\n6. Facture\n7. Termes",
        "en": "Safinum:\n1. Balance\n2. Transfer\n3. Fees\n4. History\n5. Airtime\n6. Bills\n7. Terms",
    },
    "balance": {
        "ewo": "Itan ineu a nkwap {phone}: {balance}.",
        "dua": "Moni ma pene o konto {phone}: {balance}.",
        "fr": "Votre solde ({phone}) est de {balance}.",
        "en": "Your balance ({phone}) is {balance}.",
    },
    "ask_transfer_to": {
        "ewo": "Tili dzoé nge nombo mod wa lom moni:",
        "dua": "Tila dina nga nimero ya mukusa:",
        "fr": "Nom ou numero du beneficiaire:",
        "en": "Beneficiary name or phone number:",
    },
    "ask_amount": {
        "ewo": "Itan ya lom (FCFA):",
        "dua": "Moni ma loma (FCFA):",
        "fr": "Montant en FCFA:",
        "en": "Amount in FCFA:",
    },
    "ask_fee_amount": {
        "ewo": "Itan ya fombo mbug (FCFA):",
        "dua": "Moni ma ombwa mabala (FCFA):",
        "fr": "Montant pour calculer les frais (FCFA):",
        "en": "Amount to check fees (FCFA):",
    },
    "fee_answer": {
        "ewo": "Lomo {amount}: mbug {fee}, ntolan {total}.",
        "dua": "Loma {amount}: mabala {fee}, botali {total}.",
        "fr": "Envoi {amount}: frais {fee}, total {total}.",
        "en": "Send {amount}: fee {fee}, total {total}.",
    },
    "ambiguous_benef": {
        "ewo": "Bot biba be bele dzoé di. Tob:\n{choices}",
        "dua": "Bato biba ba bene di dina. Pona:\n{choices}",
        "fr": "Plusieurs beneficiaires trouves. Choisissez:\n{choices}",
        "en": "Multiple beneficiaries found. Pick one:\n{choices}",
    },
    "confirm_transfer": {
        "ewo": "Lomo {amount} a {to}. Mbug {fee}, ntolan {total}.\n1. Yemban\n2. Vaa\n3. Tyende",
        "dua": "Loma {amount} na {to}. Mabala {fee}, botali {total}.\n1. Bamse\n2. Buka\n3. Tukwa",
        "fr": "Envoi {amount} a {to}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier",
        "en": "Send {amount} to {to}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit",
    },
    "confirm_airtime": {
        "ewo": "Kredi {operator} {amount} a {to}. Mbug {fee}, ntolan {total}.\n1. Yemban\n2. Vaa\n3. Tyende",
        "dua": "Kredi {operator} {amount} o {to}. Mabala {fee}, botali {total}.\n1. Bamse\n2. Buka\n3. Tukwa",
        "fr": "Credit {operator} {amount} au {to}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier",
        "en": "{operator} airtime {amount} to {to}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit",
    },
    "confirm_bill": {
        "ewo": "Kalara {biller} {amount}. Mbug {fee}, ntolan {total}.\n1. Yemban\n2. Vaa\n3. Tyende",
        "dua": "Kalati {biller} {amount}. Mabala {fee}, botali {total}.\n1. Bamse\n2. Buka\n3. Tukwa",
        "fr": "Facture {biller} {amount}. Frais {fee}, total {total}.\n1. Confirmer\n2. Annuler\n3. Modifier",
        "en": "{biller} bill {amount}. Fee {fee}, total {total}.\n1. Confirm\n2. Cancel\n3. Edit",
    },
    "confirmed": {
        "ewo": "Mvet o boban mben! {amount} a {to}. Ref {ref}.",
        "dua": "Ebolo e bodi! {amount} na {to}. Edun {ref}.",
        "fr": "Operation confirmee! {amount} pour {to}. Ref {ref}.",
        "en": "Confirmed! {amount} for {to}. Ref {ref}.",
    },
    "cancelled": {
        "ewo": "Mvet o vaban. Te ke itan e tsigban.",
        "dua": "Ebolo e bukabe. To moni ma si busabe.",
        "fr": "Operation annulee. Aucun montant debite.",
        "en": "Transaction cancelled. Nothing debited.",
    },
    "ask_new_amount": {
        "ewo": "Tili itan mfefe (FCFA):",
        "dua": "Tila mutango mpepe (FCFA):",
        "fr": "Entrez le nouveau montant (FCFA):",
        "en": "Enter the new amount (FCFA):",
    },
    "ask_airtime_target": {
        "ewo": "Kredi asu:\n1. Nombo wam\n2. Nombo mfe",
        "dua": "Kredi o:\n1. Nimero am\n2. Nimero mpepe",
        "fr": "Credit pour:\n1. Mon numero\n2. Autre numero",
        "en": "Airtime for:\n1. My number\n2. Another number",
    },
    "ask_airtime_phone": {
        "ewo": "Tili nombo telefon (9 chiffres):",
        "dua": "Tila nimero a telefone (9 chiffres):",
        "fr": "Numero a recharger (9 chiffres):",
        "en": "Phone number to top up (9 digits):",
    },
    "ask_biller": {
        "ewo": "Tob kalara:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
        "dua": "Pona kalati:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
        "fr": "Facturier:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
        "en": "Biller:\n1. ENEO\n2. CAMWATER\n3. CANAL\n4. CAMTEL",
    },
    "ask_term": {
        "ewo": "Za dzam wa yi yem?\n1. Mbug (frais)\n2. Nkuk (plafond)\n3. Mod a non (beneficiaire)",
        "dua": "Nje o tondi bia?\n1. Mabala (frais)\n2. Ndongo (plafond)\n3. Mukusa (beneficiaire)",
        "fr": "Quel terme expliquer?\n1. Frais\n2. Plafond\n3. Beneficiaire",
        "en": "Which term to explain?\n1. Fee\n2. Limit\n3. Beneficiary",
    },
    "term_fee": {
        "ewo": "Mbug: itan etun banki a tsig asu na a lom moni wog (ex: 50 a 400 FCFA).",
        "dua": "Mabala: moni banki e ma-nongo o bola loma (ex: 50 a 400 FCFA).",
        "fr": "Frais: petite somme retenue par la banque pour faire l'envoi (ex: 50 a 400 FCFA).",
        "en": "Fee: small amount the bank charges to process your transfer.",
    },
    "term_limit": {
        "ewo": "Nkuk: itan enen o ne dzam lom a mvet wua (500 000 FCFA).",
        "dua": "Ndongo: moni ma ndene o tondi loma ngeba ewo (500 000 FCFA).",
        "fr": "Plafond: montant maximum autorise par operation (500 000 FCFA).",
        "en": "Limit: maximum amount allowed in a single transaction (500 000 FCFA).",
    },
    "term_beneficiary": {
        "ewo": "Mod a non moni: nyi wa lom itan. Fombo dzoé ai nombo ossussua.",
        "dua": "Mukusa: moto nu ma-kusa moni mongo. Ombwa dina na nimero oboso.",
        "fr": "Beneficiaire: la personne qui recoit votre argent. Verifiez toujours son numero.",
        "en": "Beneficiary: the person receiving your money. Always check their number.",
    },
    "lang_switched": {
        "ewo": "Nkobo o tyendeban: Ewondo. {resume}",
        "dua": "Bwambo bo tukwabe: Duala. {resume}",
        "fr": "Langue changee: Francais. {resume}",
        "en": "Language switched: English. {resume}",
    },
    "history_empty": {
        "ewo": "Te ke mvet a tatan.",
        "dua": "To ebolo tatan.",
        "fr": "Aucune operation recente.",
        "en": "No recent transactions.",
    },
    "invalid_amount": {
        "ewo": "Nombo itan a ne abe. Tili nombo (ex: 5000):",
        "dua": "Mutango ma si tenge. Tila nombo (ex: 5000):",
        "fr": "Montant invalide. Tapez un nombre (ex: 5000):",
        "en": "Invalid amount. Enter a number (e.g. 5000):",
    },
    "invalid_phone": {
        "ewo": "Nombo a ne abe. 9 chiffres, ex: 699000002",
        "dua": "Nimero e si tenge. 9 chiffres, ex: 699000002",
        "fr": "Numero invalide. 9 chiffres, ex: 699000002",
        "en": "Invalid phone. 9 digits, e.g. 699000002",
    },
    "confirm_prompt_retry": {
        "ewo": "Tili 1 (Yemban), 2 (Vaa) nge 3 (Tyende).",
        "dua": "Tila 1 (Bamse), 2 (Buka) nga 3 (Tukwa).",
        "fr": "Tapez 1 (Confirmer), 2 (Annuler) ou 3 (Modifier).",
        "en": "Reply 1 (Confirm), 2 (Cancel) or 3 (Edit).",
    },
    "atm_multiple": {
        "ewo": "Nong moni a GAB: multiples 5 000 FCFA (ex: 5000, 10000).",
        "dua": "Busa moni o GAB: multiples 5 000 FCFA (ex: 5000, 10000).",
        "fr": "Retrait GAB uniquement par multiples de 5 000 FCFA.",
        "en": "ATM withdrawals must be multiples of 5,000 FCFA.",
    },
    "err_INSUFFICIENT_FUNDS": {
        "ewo": "Itan yoe e se dzam asu mvet nyi. Lomo itan etun.",
        "dua": "Moni mongo ma si kolisane. Loma moni ma siti.",
        "fr": "Solde insuffisant pour couvrir le montant et les frais. Essayez un montant plus petit.",
        "en": "Insufficient balance for this amount and fee. Try a smaller amount.",
    },
    "err_LIMIT_EXCEEDED": {
        "ewo": "Itan e lod nkuk (500 000 FCFA a mvet).",
        "dua": "Moni ma busi ndongo (500 000 FCFA).",
        "fr": "Montant superieur au plafond autorise (500 000 FCFA).",
        "en": "Amount exceeds maximum limit (500,000 FCFA).",
    },
    "err_UNKNOWN_BENEFICIARY": {
        "ewo": "Mod a nji yenban. Fombo dzoé ai nombo.",
        "dua": "Mukusa a si yenbe. Ombwa dina na nimero.",
        "fr": "Beneficiaire introuvable. Verifiez le nom ou le numero.",
        "en": "Beneficiary not found. Check name or number.",
    },
    "err_UNKNOWN_ACCOUNT": {
        "ewo": "Nkwap o nji yenban.",
        "dua": "Konto e si yenbe.",
        "fr": "Compte introuvable.",
        "en": "Account not found.",
    },
    "err_UNKNOWN_BILLER": {
        "ewo": "Isae e nji yenban. Tob ENEO, CAMWATER, CANAL nge CAMTEL.",
        "dua": "Ebolo e si biabe. Pona ENEO, CAMWATER, CANAL nga CAMTEL.",
        "fr": "Facturier inconnu. Choisissez ENEO, CAMWATER, CANAL ou CAMTEL.",
        "en": "Unknown biller. Choose ENEO, CAMWATER, CANAL or CAMTEL.",
    },
    "err_GENERIC": {
        "ewo": "Mvet o nji boban. Kele ko.",
        "dua": "Ebolo e si bolane. Kekise pene.",
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
