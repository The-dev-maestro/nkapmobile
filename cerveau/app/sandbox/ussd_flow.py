"""Moteur conversationnel multicanal SAFINUM (USSD *123#, SMS, ATM, IVR).

Respecte intégralement le contrat officiel :
- X-Trace-Id propagé sur chaque appel banque
- Confirmation dans un tour séparé (jamais dans le même tour que POST /transactions)
- 13 intentions officielles en MAJUSCULES
- Zéro devinette sur montant ou bénéficiaire homonyme (CLARIFICATION_NEEDED)
- Correction avant confirmation (annulation pending + recalcul frais + nouvelle relecture)
- Changement de langue en cours de session sans perte de contexte
- GSM-7 strict <= 182 septets (USSD) / <= 160 septets (SMS)
- Sessions persistées en SQLite WAL (partagées entre workers) + reprise lecture seule via ussd_text
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

from app.sandbox.bank_client import SafinumBankClient
from app.sandbox.gsm7 import fit_gsm7, gsm7_length
from app.sandbox.language import (
    _norm,
    detect_biller,
    detect_intent_keyword,
    detect_language_switch,
    detect_term_question,
    parse_amount,
    parse_phone,
    render_phrase,
    resolve_lang,
)

LOCK = threading.Lock()
SESSION_TTL_S = 180

_OP_STATE_KEYS = (
    "op_type",
    "to",
    "to_name",
    "amount",
    "fee",
    "total",
    "biller",
    "operator",
    "candidates",
    "reference",
    "in_correction",
    "needs_pending_lookup",
    "fee_kind",
)

_BUSINESS_ERRORS = {
    "INSUFFICIENT_FUNDS",
    "LIMIT_EXCEEDED",
    "UNKNOWN_BENEFICIARY",
    "UNKNOWN_ACCOUNT",
    "UNKNOWN_BILLER",
}


class SqliteSessionStore(MutableMapping[str, dict[str, Any]]):
    """Store de sessions USSD partagé entre tous les workers (SQLite WAL) avec repli mémoire."""

    def __init__(self, db_path: str | Path | None = None):
        raw_path = db_path or os.getenv("NKAP_USSD_SESSION_DB") or (
            Path(tempfile.gettempdir()) / "nkap_ussd_sessions.sqlite3"
        )
        self.db_path = Path(raw_path)
        self._lock = threading.Lock()
        self._mem: dict[str, dict[str, Any]] = {}
        self._use_sqlite = False
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ussd_sessions (
                        session_id TEXT PRIMARY KEY,
                        state_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
            self._use_sqlite = True
        except Exception:
            self._use_sqlite = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def __getitem__(self, key: str) -> dict[str, Any]:
        with self._lock:
            if not self._use_sqlite:
                return dict(self._mem[key])
            try:
                with self._connect() as conn:
                    row = conn.execute(
                        "SELECT state_json FROM ussd_sessions WHERE session_id = ?",
                        (key,),
                    ).fetchone()
                if row is None:
                    raise KeyError(key)
                data = json.loads(row[0])
                return data if isinstance(data, dict) else {}
            except KeyError:
                raise
            except Exception:
                return dict(self._mem[key])

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, ensure_ascii=False)
        updated_at = float(value.get("updated_at") or time.time())
        with self._lock:
            self._mem[key] = dict(value)
            if not self._use_sqlite:
                return
            try:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO ussd_sessions (session_id, state_json, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(session_id) DO UPDATE SET
                            state_json = excluded.state_json,
                            updated_at = excluded.updated_at
                        """,
                        (key, encoded, updated_at),
                    )
            except Exception:
                pass

    def __delitem__(self, key: str) -> None:
        with self._lock:
            had_mem = key in self._mem
            self._mem.pop(key, None)
            if not self._use_sqlite:
                if not had_mem:
                    raise KeyError(key)
                return
            try:
                with self._connect() as conn:
                    cur = conn.execute(
                        "DELETE FROM ussd_sessions WHERE session_id = ?",
                        (key,),
                    )
                if cur.rowcount == 0 and not had_mem:
                    raise KeyError(key)
            except KeyError:
                raise
            except Exception:
                if not had_mem:
                    raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            if not self._use_sqlite:
                return iter(list(self._mem.keys()))
            try:
                with self._connect() as conn:
                    rows = conn.execute("SELECT session_id FROM ussd_sessions").fetchall()
                return iter([r[0] for r in rows])
            except Exception:
                return iter(list(self._mem.keys()))

    def __len__(self) -> int:
        with self._lock:
            if not self._use_sqlite:
                return len(self._mem)
            try:
                with self._connect() as conn:
                    row = conn.execute("SELECT COUNT(*) FROM ussd_sessions").fetchone()
                return int(row[0]) if row else 0
            except Exception:
                return len(self._mem)

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()
            if not self._use_sqlite:
                return
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM ussd_sessions")
            except Exception:
                pass

    def prune(self, now: float, max_age_s: float) -> None:
        cutoff = now - max_age_s
        with self._lock:
            expired = [sid for sid, st in self._mem.items() if float(st.get("updated_at") or 0) < cutoff]
            for sid in expired:
                self._mem.pop(sid, None)
            if not self._use_sqlite:
                return
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM ussd_sessions WHERE updated_at < ?", (cutoff,))
            except Exception:
                pass


SESSIONS: MutableMapping[str, dict[str, Any]] = SqliteSessionStore()


def _money(amount: Any) -> str:
    try:
        return f"{int(round(float(amount or 0))):,} FCFA".replace(",", " ")
    except Exception:
        return f"{amount} FCFA"


def _local_phone(phone: str | None) -> str:
    return re.sub(r"^\+?237", "", str(phone or ""))


def _prune_sessions(now: float) -> None:
    if isinstance(SESSIONS, SqliteSessionStore):
        SESSIONS.prune(now, SESSION_TTL_S * 3)
        return
    expired = [sid for sid, st in list(SESSIONS.items()) if now - float(st.get("updated_at") or 0) > SESSION_TTL_S * 3]
    for sid in expired:
        SESSIONS.pop(sid, None)


def _clear_op_state(state: dict[str, Any]) -> None:
    for k in _OP_STATE_KEYS:
        state.pop(k, None)


def _confirm_options(op: str) -> list[str]:
    if op == "transfer":
        return ["Confirmer", "Annuler", "Modifier montant", "Modifier destinataire"]
    return ["Confirmer", "Annuler", "Modifier montant"]


def _is_cancel_on_confirm(text: str, kw_intent: str | None) -> bool:
    if text == "2" or kw_intent == "CANCEL":
        return True
    # En Duala, "Sumua" est le libellé affiché pour "2. Sumua" (Annuler) sur l'écran de confirmation
    return _norm(text) in {"sumua", "2. sumua", "2 sumua"}


def _detect_fee_kind(text: str) -> str:
    n = _norm(text)
    if any(re.search(rf"\b{k}\b", n) for k in ("facture", "bill", "eneo", "camwater", "canal", "camtel", "kalara", "kalati")):
        return "bill"
    if any(re.search(rf"\b{k}\b", n) for k in ("retrait", "retirer", "withdraw", "gab", "atm")):
        return "withdrawal"
    if any(re.search(rf"\b{k}\b", n) for k in ("credit", "airtime", "recharge", "kredi", "ikola", "ebale")):
        return "airtime"
    return "transfer"


def _reply(
    text: str,
    intent: str,
    lang: str,
    *,
    parameters: dict[str, Any] | None = None,
    options: list[str] | None = None,
    end: bool = False,
    transaction: dict[str, Any] | None = None,
    max_septets: int = 182,
) -> dict[str, Any]:
    return {
        "response": {
            "text": fit_gsm7(text, max_septets=max_septets),
            "end_session": end,
            "options": [fit_gsm7(o, max_septets=40) for o in (options or [])],
        },
        "interpretation": {
            "intent": intent,
            "parameters": parameters or {},
            "language": lang,
        },
        "transaction": transaction or {"id": None, "status": "none"},
    }


def _bank_error(
    data: dict[str, Any],
    intent: str,
    lang: str,
    reference: str | None = None,
    max_septets: int = 182,
) -> dict[str, Any]:
    code = str((data or {}).get("error") or "GENERIC").upper()
    key = f"err_{code}" if code in _BUSINESS_ERRORS else "err_GENERIC"
    txt, declared = render_phrase(key, lang, max_septets=max_septets)
    return _reply(
        txt,
        intent,
        declared,
        parameters={"error": code},
        end=True,
        transaction={"id": reference, "status": "failed"} if reference else None,
        max_septets=max_septets,
    )


def _format_recap(state: dict[str, Any], lang: str, max_septets: int) -> tuple[str, str]:
    op = state.get("op_type", "transfer")
    fee_s = _money(state.get("fee", 0))
    amt_s = _money(state.get("amount", 0))
    tot_s = _money(state.get("total", state.get("amount", 0)))
    if op == "airtime":
        return render_phrase(
            "confirm_airtime",
            lang,
            max_septets=max_septets,
            operator=state.get("operator") or "",
            amount=amt_s,
            to=_local_phone(state.get("to")),
            fee=fee_s,
            total=tot_s,
        )
    if op == "bill":
        return render_phrase(
            "confirm_bill",
            lang,
            max_septets=max_septets,
            biller=state.get("biller") or "",
            amount=amt_s,
            fee=fee_s,
            total=tot_s,
        )
    if op == "withdrawal":
        return render_phrase(
            "confirm_withdrawal",
            lang,
            max_septets=max_septets,
            amount=amt_s,
            fee=fee_s,
            total=tot_s,
        )
    to_label = state.get("to_name") or _local_phone(state.get("to"))
    return render_phrase(
        "confirm_transfer",
        lang,
        max_septets=max_septets,
        amount=amt_s,
        to=to_label,
        fee=fee_s,
        total=tot_s,
    )


def _format_candidates(cands: list[dict[str, Any]], lang: str, max_septets: int) -> tuple[str, str, list[dict[str, Any]]]:
    """Formate la liste de bénéficiaires homonymes sans jamais tronquer une option."""
    shown: list[dict[str, Any]] = []
    lines: list[str] = []
    header_probe, declared = render_phrase("ambiguous_benef", lang, max_septets=max_septets, choices="")
    budget = max(40, max_septets - gsm7_length(header_probe))
    used = 0
    for cand in cands[:4]:
        idx = len(shown) + 1
        name = str(cand.get("name") or "?").strip()
        ph = _local_phone(cand.get("phone"))
        suffix = f" ({ph})" if ph else ""
        if len(name) > 22:
            name = name[:21].rstrip() + "."
        line = f"{idx}. {name}{suffix}"
        cost = gsm7_length(line) + (1 if lines else 0)
        if lines and used + cost > budget:
            break
        lines.append(line)
        shown.append(cand)
        used += cost
    if not shown and cands:
        shown = cands[:2]
        lines = [f"{i}. {str(c.get('name', '?'))[:18]} ({_local_phone(c.get('phone'))})" for i, c in enumerate(shown, 1)]
    txt, declared = render_phrase("ambiguous_benef", lang, max_septets=max_septets, choices="\n".join(lines))
    return txt, declared, shown


def _create_pending_operation(
    state: dict[str, Any],
    phone: str,
    bank: SafinumBankClient,
    lang: str,
    intent: str,
    max_septets: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    op = state.get("op_type", "transfer")
    amount = int(state["amount"])
    if dry_run:
        state["step"] = "confirm"
        state["needs_pending_lookup"] = True
        state.pop("in_correction", None)
        return _reply("", intent, resolve_lang(lang), max_septets=max_septets)

    # Annule une éventuelle ancienne opération pending avant de créer son remplacement
    old_ref = state.get("reference")
    if old_ref:
        bank.cancel(old_ref)
        state["reference"] = None

    body: dict[str, Any] = {"type": op, "from": phone, "amount": amount}
    if op in {"transfer", "airtime"}:
        body["to"] = state["to"]
    elif op == "bill":
        body["biller"] = state["biller"]

    ok, _status, tx = bank.create_transaction(body)
    if not ok:
        return _bank_error(tx, intent, lang, max_septets=max_septets)

    ref = tx.get("id") or tx.get("reference")
    fee = tx.get("fee", 0)
    total = tx.get("total")
    if total is None:
        total = amount + int(fee or 0)

    state["step"] = "confirm"
    state["reference"] = ref
    state["fee"] = fee
    state["total"] = total
    state.pop("in_correction", None)
    state.pop("needs_pending_lookup", None)
    if tx.get("operator"):
        state["operator"] = tx["operator"]

    txt, declared = _format_recap(state, lang, max_septets)
    params: dict[str, Any] = {"amount": amount, "currency": "XAF", "fee": state["fee"], "total": state["total"]}
    if state.get("to"):
        params["to"] = state["to"]
    if state.get("to_name"):
        params["beneficiary"] = state["to_name"]
    if state.get("biller"):
        params["biller"] = state["biller"]
    return _reply(
        txt,
        intent,
        declared,
        parameters=params,
        options=_confirm_options(op),
        transaction={"id": state["reference"], "status": "pending"},
        max_septets=max_septets,
    )


def _do_balance(phone: str, bank: SafinumBankClient, lang: str, max_septets: int) -> dict[str, Any]:
    ok, _st, data = bank.balance(phone)
    if not ok:
        return _bank_error(data, "BALANCE_INQUIRY", lang, max_septets=max_septets)
    bal = data.get("balance", 0)
    txt, declared = render_phrase("balance", lang, max_septets=max_septets, phone=_local_phone(phone), balance=_money(bal))
    return _reply(
        txt,
        "BALANCE_INQUIRY",
        declared,
        parameters={"account": phone, "balance": bal, "currency": "XAF"},
        end=True,
        max_septets=max_septets,
    )


def _do_fees(amount: int, bank: SafinumBankClient, lang: str, max_septets: int, kind: str = "transfer") -> dict[str, Any]:
    ok, _st, data = bank.fees(kind, amount)
    if not ok:
        return _bank_error(data, "FEE_INQUIRY", lang, max_septets=max_septets)
    fee = data.get("fee", 0)
    total = data.get("total", amount + fee)
    txt, declared = render_phrase(
        "fee_answer",
        lang,
        max_septets=max_septets,
        amount=_money(amount),
        fee=_money(fee),
        total=_money(total),
    )
    return _reply(
        txt,
        "FEE_INQUIRY",
        declared,
        parameters={"type": kind, "amount": amount, "fee": fee, "total": total, "currency": "XAF"},
        end=True,
        max_septets=max_septets,
    )


def _do_history(phone: str, bank: SafinumBankClient, lang: str, max_septets: int) -> dict[str, Any]:
    ok, _st, data = bank.history(phone, limit=4)
    if not ok:
        return _bank_error(data, "TRANSACTION_HISTORY", lang, max_septets=max_septets)
    txs = data.get("transactions") or data.get("items") or data.get("data") or []
    if not txs:
        txt, declared = render_phrase("history_empty", lang, max_septets=max_septets)
        return _reply(txt, "TRANSACTION_HISTORY", declared, parameters={"count": 0}, end=True, max_septets=max_septets)

    lines = []
    for item in txs[:3]:
        kind = str(item.get("type") or "op")[:8]
        amt = _money(item.get("amount", 0))
        st = str(item.get("status") or "")[:7]
        raw_who = (
            item.get("beneficiary")
            or item.get("to_name")
            or item.get("biller")
            or item.get("operator")
            or _local_phone(item.get("to"))
            or ""
        )
        if isinstance(raw_who, dict):
            raw_who = raw_who.get("name") or _local_phone(raw_who.get("phone")) or ""
        who = str(raw_who)[:12]
        lines.append(f"- {kind} {who} {amt} ({st})".replace("  ", " ").strip())
    declared = resolve_lang(lang)
    header = {"ewo": "Itang mvet:", "dua": "Miango:", "en": "History:"}.get(declared, "Historique:")
    return _reply(
        header + "\n" + "\n".join(lines),
        "TRANSACTION_HISTORY",
        declared,
        parameters={"count": len(txs)},
        end=True,
        max_septets=max_septets,
    )


def _clean_beneficiary_query(query: str) -> str:
    clean_q = re.sub(
        r"\b(?:je|veux|voudrais|aimerais|souhaite|faire|un|une|envoyer|envoie|transfert|transferer|transfer|send|"
        r"lomo|lom|loma|lomea|tombise|moni|a|au|aux|pour|vers|chez|to|o|dina|la|le|de|du|des|na|ni|tombele|asu|"
        r"fcfa|xaf|francs|f|stp|merci|please|want|money|"
        r"corriger|corrige|modifier|modifie|changer|change|finalement|plutot|tyende|tukwa|edit|"
        r"beneficiaire|destinataire|recipient|mod|mukusedi|mukusa|numero|nom)\b",
        " ",
        query or "",
        flags=re.IGNORECASE,
    )
    clean_q = re.sub(r"\b\d[\d\s.]*\b", " ", clean_q)
    return re.sub(r"\s+", " ", clean_q).strip(" ,.-:;?!")


def _filter_by_tokens(items: list[dict[str, Any]], clean_q: str) -> list[dict[str, Any]]:
    """Si la requête a plusieurs mots (ex: 'Blaise Mukete' ou 'Mukete Blaise'), privilégie les correspondances complètes."""
    q_norm = _norm(clean_q)
    q_tokens = [t for t in q_norm.split() if len(t) >= 2]
    if not q_tokens or len(items) <= 1:
        return items

    exact_name = [it for it in items if _norm(it.get("name")) == q_norm]
    if exact_name:
        return exact_name

    if len(q_tokens) >= 2:
        all_match = [
            it for it in items
            if all(tok in _norm(it.get("name")) for tok in q_tokens)
        ]
        if all_match:
            return all_match
    return items


def _resolve_beneficiary_or_clarify(
    state: dict[str, Any],
    query: str,
    phone: str,
    bank: SafinumBankClient,
    lang: str,
    max_septets: int,
    *,
    ask_phrase_key: str = "ask_transfer_to",
    fallback_step: str = "transfer_to",
) -> dict[str, Any] | None:
    """Résout un bénéficiaire ; renvoie une réponse CLARIFICATION_NEEDED si ambigu ou introuvable, sinon None (state mis à jour)."""
    parsed_phone = parse_phone(query)
    if parsed_phone:
        state["to"] = parsed_phone
        state["to_name"] = _local_phone(parsed_phone)
        return None

    clean_q = _clean_beneficiary_query(query)
    if not clean_q:
        state["step"] = fallback_step
        txt, declared = render_phrase(ask_phrase_key, lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    # IMPORTANT : GET /beneficiaries?q=&phone= cherche par nom OU par numéro du bénéficiaire
    # (ne JAMAIS passer le numéro de l'expéditeur `phone` dans `phone=`, sinon l'API renvoie [] !)
    ok, _st, data = bank.beneficiaries(clean_q)
    if not ok:
        return _bank_error(data, "TRANSFER", lang, max_septets=max_septets)

    raw_items = list(data.get("beneficiaries") or data.get("items") or data.get("data") or [])
    # Si la saisie contient "Prénom Nom" (ou "Nom Prénom") et ne renvoie rien, tente chaque jeton >= 2 car.
    if not raw_items and " " in clean_q:
        seen_toks: set[str] = set()
        for tok in clean_q.split():
            tl = tok.lower()
            if len(tok) < 2 or tl in seen_toks:
                continue
            seen_toks.add(tl)
            ok2, _st2, data2 = bank.beneficiaries(tok)
            if ok2:
                found = data2.get("beneficiaries") or data2.get("items") or data2.get("data") or []
                if found:
                    raw_items.extend(found)
                    # Si on a déjà une correspondance qui contient tous les mots, inutile d'interroger davantage
                    if len(_filter_by_tokens(raw_items, clean_q)) == 1:
                        break

    # Déduplique par téléphone (l'API SAFINUM peut renvoyer un même bénéficiaire sur plusieurs institutions)
    # et évite de proposer l'expéditeur lui-même quand d'autres bénéficiaires correspondent.
    dedup_by_phone: dict[str, dict[str, Any]] = {}
    for it in raw_items:
        ph = str(it.get("phone") or "").strip()
        if not ph:
            continue
        if ph not in dedup_by_phone or str(it.get("institution") or "").upper() == "SAFINUM":
            dedup_by_phone[ph] = it
    items = list(dedup_by_phone.values()) if dedup_by_phone else raw_items
    non_self = [it for it in items if str(it.get("phone") or "").strip() != phone]
    if non_self:
        items = non_self

    # Filtre par correspondance complète multi-mots (ex: "Blaise Mukete" ou "Mukete Blaise" -> 1 résultat exact)
    items = _filter_by_tokens(items, clean_q)

    if not items:
        return _bank_error({"error": "UNKNOWN_BENEFICIARY"}, "TRANSFER", lang, max_septets=max_septets)
    if len(items) > 1:
        txt, declared, shown = _format_candidates(items, lang, max_septets)
        state["step"] = "transfer_pick_benef"
        state["candidates"] = shown
        return _reply(
            txt,
            "CLARIFICATION_NEEDED",
            declared,
            parameters={"query": clean_q, "matches": len(items)},
            options=[str(c.get("name", i)) for i, c in enumerate(shown, start=1)],
            max_septets=max_septets,
        )

    hit = items[0]
    state["to"] = hit.get("phone")
    state["to_name"] = hit.get("name") or _local_phone(hit.get("phone"))
    return None


def _render_resume_for_step(state: dict[str, Any], lang: str, max_septets: int) -> str:
    """Re-rend l'invite courante dans la nouvelle langue sans perdre le contexte."""
    step = state.get("step", "idle")
    if step == "confirm" and (state.get("reference") or state.get("amount")):
        txt, _ = _format_recap(state, lang, max_septets)
        return txt
    if step == "transfer_to":
        txt, _ = render_phrase("ask_transfer_to", lang, max_septets=max_septets)
        return txt
    if step == "correction_beneficiary":
        txt, _ = render_phrase("ask_new_beneficiary", lang, max_septets=max_septets)
        return txt
    if step == "correction_amount":
        txt, _ = render_phrase("ask_new_amount", lang, max_septets=max_septets)
        return txt
    if step in {"transfer_amount", "airtime_amount", "bill_amount"}:
        txt, _ = render_phrase("ask_amount", lang, max_septets=max_septets)
        return txt
    if step == "transfer_pick_benef" and state.get("candidates"):
        txt, _, _ = _format_candidates(state["candidates"], lang, max_septets)
        return txt
    if step == "fee_amount":
        txt, _ = render_phrase("ask_fee_amount", lang, max_septets=max_septets)
        return txt
    if step == "airtime_target":
        txt, _ = render_phrase("ask_airtime_target", lang, max_septets=max_septets)
        return txt
    if step == "airtime_phone":
        txt, _ = render_phrase("ask_airtime_phone", lang, max_septets=max_septets)
        return txt
    if step == "bill_pick":
        txt, _ = render_phrase("ask_biller", lang, max_septets=max_septets)
        return txt
    if step == "term_pick":
        txt, _ = render_phrase("ask_term", lang, max_septets=max_septets)
        return txt
    state["step"] = "menu"
    txt, _ = render_phrase("menu", lang, max_septets=max_septets)
    return txt


def _lookup_pending_transaction(state: dict[str, Any], phone: str, bank: SafinumBankClient) -> bool:
    """En cas de reprise sur une autre réplique stateless, retrouve la transaction pending côté banque (GET lecture seule)."""
    ok, _st, data = bank.history(phone, limit=5)
    if not ok:
        return False
    txs = data.get("transactions") or data.get("items") or data.get("data") or []
    op = state.get("op_type", "transfer")
    target_amt = int(state.get("amount") or 0)
    target_to = str(state.get("to") or "").strip()
    target_biller = str(state.get("biller") or "").upper().strip()

    for tx in txs:
        if str(tx.get("status") or "").lower() != "pending":
            continue
        tx_type = str(tx.get("type") or "").lower()
        if tx_type and tx_type != op:
            continue
        if target_amt and int(round(float(tx.get("amount") or 0))) != target_amt:
            continue
        if op in {"transfer", "airtime"} and target_to:
            tx_to = str(tx.get("to") or "").strip()
            if tx_to and _local_phone(tx_to) != _local_phone(target_to):
                continue
        if op == "bill" and target_biller:
            tx_biller = str(tx.get("biller") or "").upper().strip()
            if tx_biller and tx_biller != target_biller:
                continue
        ref = tx.get("id") or tx.get("reference")
        if ref:
            state["reference"] = ref
            state["fee"] = tx.get("fee", state.get("fee", 0))
            state["total"] = tx.get("total", target_amt + int(state["fee"] or 0))
            if tx.get("operator"):
                state["operator"] = tx["operator"]
            state.pop("needs_pending_lookup", None)
            return True
    return False


def _recover_state_from_ussd_prefix(
    prefix: str,
    phone: str,
    bank: SafinumBankClient,
    initial_lang: str,
    max_septets: int,
) -> dict[str, Any]:
    """Rejoue en lecture seule les tours USSD précédents si une réplique stateless a perdu la session."""
    replay_state: dict[str, Any] = {"step": "menu", "lang": initial_lang}
    for seg in prefix.split("*"):
        seg_clean = seg.strip()
        cur_lang = replay_state.get("lang") or initial_lang
        switched = detect_language_switch(seg_clean)
        if switched:
            replay_state["lang"] = switched
            replay_state["lang_locked"] = True
            continue
        allow_bare_term = replay_state.get("step") not in {
            "transfer_to",
            "correction_beneficiary",
            "transfer_amount",
            "correction_amount",
            "airtime_phone",
            "airtime_amount",
            "bill_amount",
            "fee_amount",
        }
        if detect_term_question(seg_clean, allow_bare=allow_bare_term):
            continue
        _route_turn(replay_state, seg_clean, phone, bank, cur_lang, "ussd", max_septets, dry_run=True)

    if replay_state.get("step") == "confirm" and replay_state.get("needs_pending_lookup"):
        _lookup_pending_transaction(replay_state, phone, bank)
    return replay_state


def handle_channel_turn(
    payload: dict[str, Any],
    trace_id: str | None = None,
    bank_client: SafinumBankClient | None = None,
) -> dict[str, Any]:
    """Point d'entrée unique pour USSD, SMS, ATM et IVR sur la passerelle SAFINUM."""
    channel = str(payload.get("channel") or "ussd").lower()
    constraints = payload.get("constraints") or {}
    max_septets = int(constraints.get("max_chars") or (160 if channel == "sms" else 182))
    phone = str(payload.get("phone") or payload.get("phoneNumber") or "").strip()
    session_id = str(payload.get("session_id") or payload.get("sessionId") or f"{channel}_{phone or 'anon'}").strip()
    req_lang = payload.get("language")
    inp = payload.get("input") or {}
    ussd_text = str(inp.get("ussd_text") or "").strip() if isinstance(inp, dict) else ""
    if isinstance(inp, dict) and inp.get("text") is not None:
        raw_text = str(inp.get("text") or "").strip()
    elif ussd_text:
        raw_text = ussd_text.split("*")[-1].strip()
    else:
        raw_text = ""

    bank = bank_client or SafinumBankClient(
        base_url=(payload.get("bank_api") or {}).get("base_url"),
        trace_id=trace_id or payload.get("trace_id"),
    )

    now = time.time()
    with LOCK:
        _prune_sessions(now)
        state = dict(SESSIONS.get(session_id) or {"step": "idle"})

    # Détection de désynchronisation sur déploiement multi-répliques stateless via input.ussd_text
    if channel == "ussd" and ussd_text and "*" in ussd_text:
        prefix = ""
        if raw_text and ussd_text.endswith(f"*{raw_text}"):
            prefix = ussd_text[: -(len(raw_text) + 1)]
        elif raw_text == "" and ussd_text.endswith("*"):
            prefix = ussd_text[:-1]
        in_sync = state.get("step") != "idle" and state.get("last_ussd_text") == prefix
        if prefix and not in_sync:
            state = _recover_state_from_ussd_prefix(
                prefix, phone, bank, resolve_lang(req_lang), max_septets
            )

    if req_lang and not state.get("lang_locked"):
        state["lang"] = resolve_lang(req_lang)
    lang = state.get("lang") or resolve_lang(req_lang)

    # 1. Changement de langue en cours de session SANS perdre l'opération ni l'étape en cours
    switched = detect_language_switch(raw_text)
    if switched:
        state["lang"] = switched
        state["lang_locked"] = True
        prefix_probe, _ = render_phrase("lang_switched", switched, max_septets=max_septets, resume="")
        resume_budget = max(60, max_septets - gsm7_length(prefix_probe))
        resume_txt = _render_resume_for_step(state, switched, resume_budget)
        txt, declared = render_phrase("lang_switched", switched, max_septets=max_septets, resume=resume_txt)
        res = _reply(
            txt,
            "LANGUAGE_SWITCH",
            declared,
            parameters={"language": switched},
            transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
            max_septets=max_septets,
        )
        if channel == "ussd" and isinstance(inp, dict) and inp.get("ussd_text") is not None:
            state["last_ussd_text"] = ussd_text
        _save_state(session_id, state, res, channel, now)
        return res

    # 2. Explication de terminologie financière à tout moment (sans détourner un nom de bénéficiaire ou une saisie)
    allow_bare_term = state.get("step") not in {
        "transfer_to",
        "correction_beneficiary",
        "transfer_amount",
        "correction_amount",
        "airtime_phone",
        "airtime_amount",
        "bill_amount",
        "fee_amount",
    }
    term = detect_term_question(raw_text, allow_bare=allow_bare_term)
    if term:
        txt, declared = render_phrase(f"term_{term}", lang, max_septets=max_septets)
        res = _reply(
            txt,
            "TERM_EXPLANATION",
            declared,
            parameters={"term": term},
            end=(channel == "sms"),
            transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
            max_septets=max_septets,
        )
        if channel == "ussd" and isinstance(inp, dict) and inp.get("ussd_text") is not None:
            state["last_ussd_text"] = ussd_text
        _save_state(session_id, state, res, channel, now)
        return res

    res = _route_turn(state, raw_text, phone, bank, lang, channel, max_septets)
    if channel == "ussd" and isinstance(inp, dict) and inp.get("ussd_text") is not None:
        state["last_ussd_text"] = ussd_text
    _save_state(session_id, state, res, channel, now)
    return res


def _save_state(session_id: str, state: dict[str, Any], res: dict[str, Any], channel: str, now: float) -> None:
    if channel == "sms":
        return
    with LOCK:
        if res["response"]["end_session"]:
            SESSIONS.pop(session_id, None)
        else:
            state["updated_at"] = now
            SESSIONS[session_id] = state


def _cancel_pending_reply(
    state: dict[str, Any],
    bank: SafinumBankClient,
    lang: str,
    max_septets: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    ref = state.get("reference")
    if dry_run:
        _clear_op_state(state)
        state["step"] = "menu"
        return _reply("", "CANCEL", resolve_lang(lang), end=True, max_septets=max_septets)
    if ref:
        ok, _st, data = bank.cancel(ref)
        if not ok:
            return _bank_error(data, "CANCEL", lang, reference=ref, max_septets=max_septets)
    txt, declared = render_phrase("cancelled", lang, max_septets=max_septets)
    return _reply(
        txt,
        "CANCEL",
        declared,
        parameters={"transaction_id": ref} if ref else {},
        end=True,
        transaction={"id": ref, "status": "cancelled"} if ref else {"id": None, "status": "none"},
        max_septets=max_septets,
    )


def _apply_amount_correction(
    state: dict[str, Any],
    new_amt: int,
    phone: str,
    bank: SafinumBankClient,
    lang: str,
    max_septets: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        state["step"] = "confirm"
        state["amount"] = new_amt
        state["needs_pending_lookup"] = True
        return _reply("", "CORRECTION", resolve_lang(lang), max_septets=max_septets)

    if state.get("reference") and callable(getattr(bank, "update", None)):
        res_u = bank.update(state["reference"], {"amount": new_amt})
        if isinstance(res_u, tuple) and len(res_u) == 3:
            ok_u, st_u, tx_u = res_u
        else:
            ok_u, st_u, tx_u = False, 0, {}
        if ok_u and isinstance(tx_u, dict) and (tx_u.get("id") or tx_u.get("reference")):
            state["step"] = "confirm"
            state["amount"] = int(tx_u.get("amount", new_amt))
            state["fee"] = tx_u.get("fee", 0)
            state["total"] = tx_u.get("total", state["amount"] + int(state["fee"] or 0))
            txt, declared = _format_recap(state, lang, max_septets)
            return _reply(
                txt,
                "CORRECTION",
                declared,
                parameters={"amount": state["amount"], "fee": state["fee"], "total": state["total"], "currency": "XAF"},
                options=_confirm_options(state.get("op_type", "transfer")),
                transaction={"id": state["reference"], "status": "pending"},
                max_septets=max_septets,
            )
        # Si la banque rejette pour erreur métier (solde insuffisant, plafond), renvoie l'erreur sans double appel
        err_code = str((tx_u or {}).get("error") or "").upper() if isinstance(tx_u, dict) else ""
        if not ok_u and err_code in _BUSINESS_ERRORS and st_u not in {404, 405, 501}:
            return _bank_error(tx_u, "CORRECTION", lang, reference=state.get("reference"), max_septets=max_septets)

    state["amount"] = new_amt
    return _create_pending_operation(state, phone, bank, lang, "CORRECTION", max_septets, dry_run=dry_run)


def _route_turn(
    state: dict[str, Any],
    text: str,
    phone: str,
    bank: SafinumBankClient,
    lang: str,
    channel: str,
    max_septets: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    step = state.get("step", "idle")
    kw_intent = detect_intent_keyword(text)

    # Ouverture session USSD (*123#)
    if text == "" and step != "confirm":
        _clear_op_state(state)
        state["step"] = "menu"
        txt, declared = render_phrase("menu", lang, max_septets=max_septets)
        return _reply(txt, "UNKNOWN", declared, options=["Solde", "Transfert", "Frais", "Historique", "Credit", "Facture", "Termes"], max_septets=max_septets)

    # Retour au menu principal depuis un sous-menu (hors écran de confirmation)
    if step not in {"idle", "menu", "confirm"} and _norm(text) in {"0", "menu", "retour", "back"}:
        _clear_op_state(state)
        state["step"] = "menu"
        txt, declared = render_phrase("menu", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, options=["Solde", "Transfert", "Frais", "Historique", "Credit", "Facture", "Termes"], max_septets=max_septets)

    # ── Étape Confirmation (tour séparé obligatoire + Correction avant confirmation) ──
    if step == "confirm":
        if text == "1" or kw_intent == "CONFIRM":
            if dry_run:
                _clear_op_state(state)
                state["step"] = "menu"
                return _reply("", "CONFIRM", resolve_lang(lang), end=True, max_septets=max_septets)
            if not state.get("reference"):
                # Sécurité contrat : ne jamais créer et confirmer dans le même tour !
                if state.get("amount"):
                    return _create_pending_operation(state, phone, bank, lang, "TRANSFER", max_septets)
                _clear_op_state(state)
                state["step"] = "menu"
                txt, declared = render_phrase("menu", lang, max_septets=max_septets)
                return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
            ok, _st, tx = bank.confirm(state["reference"])
            if not ok:
                return _bank_error(tx, "CONFIRM", lang, reference=state.get("reference"), max_septets=max_septets)
            op = state.get("op_type", "transfer")
            to_lbl = (
                "GAB"
                if op == "withdrawal"
                else (state.get("to_name") or state.get("biller") or _local_phone(tx.get("to") or state.get("to")))
            )
            ref = tx.get("id") or tx.get("reference") or state["reference"]
            txt, declared = render_phrase("confirmed", lang, max_septets=max_septets, amount=_money(tx.get("amount") or state.get("amount")), to=to_lbl, ref=ref)
            return _reply(
                txt,
                "CONFIRM",
                declared,
                parameters={"transaction_id": ref},
                end=True,
                transaction={"id": ref, "status": "confirmed"},
                max_septets=max_septets,
            )

        if _is_cancel_on_confirm(text, kw_intent):
            return _cancel_pending_reply(state, bank, lang, max_septets, dry_run=dry_run)

        if text == "4" and state.get("op_type", "transfer") == "transfer":
            state["step"] = "correction_beneficiary"
            state["in_correction"] = True
            txt, declared = render_phrase("ask_new_beneficiary", lang, max_septets=max_septets)
            return _reply(
                txt,
                "CORRECTION",
                declared,
                transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
                max_septets=max_septets,
            )

        if text == "3" or kw_intent == "CORRECTION":
            new_amt = None if text == "3" else parse_amount(text)
            new_phone = None if text == "3" else parse_phone(text)
            benef_clean = "" if text == "3" else _clean_beneficiary_query(text)
            wants_benef_word = bool(
                text != "3"
                and state.get("op_type", "transfer") == "transfer"
                and re.search(r"\b(?:beneficiaire|destinataire|recipient|mod|mukusedi|mukusa|numero|nom)\b", _norm(text))
            )

            # 1. Correction conjointe bénéficiaire + montant (ex: "plutot 10000 a Brenda")
            if state.get("op_type", "transfer") == "transfer" and new_amt and (new_phone or len(benef_clean) >= 2):
                state["in_correction"] = True
                state["amount"] = new_amt
                err_or_clarify = _resolve_beneficiary_or_clarify(
                    state, new_phone or benef_clean, phone, bank, lang, max_septets,
                    ask_phrase_key="ask_new_beneficiary", fallback_step="correction_beneficiary",
                )
                if err_or_clarify:
                    return err_or_clarify
                return _create_pending_operation(state, phone, bank, lang, "CORRECTION", max_septets, dry_run=dry_run)

            # 2. Correction directe de montant via POST /transactions/{ref}/update si disponible (sinon cancel + recreate)
            if new_amt:
                return _apply_amount_correction(state, new_amt, phone, bank, lang, max_septets, dry_run=dry_run)

            # 3. Correction de bénéficiaire avant confirmation (ex: "modifier beneficiaire Franck" / "plutot a Carine")
            if text != "3" and state.get("op_type", "transfer") == "transfer" and (new_phone or len(benef_clean) >= 2):
                state["in_correction"] = True
                err_or_clarify = _resolve_beneficiary_or_clarify(
                    state, new_phone or benef_clean, phone, bank, lang, max_septets,
                    ask_phrase_key="ask_new_beneficiary", fallback_step="correction_beneficiary",
                )
                if err_or_clarify:
                    return err_or_clarify
                return _create_pending_operation(state, phone, bank, lang, "CORRECTION", max_septets, dry_run=dry_run)

            # 4. Demande explicite de modifier le destinataire sans encore donner le nom
            if wants_benef_word:
                state["step"] = "correction_beneficiary"
                state["in_correction"] = True
                txt, declared = render_phrase("ask_new_beneficiary", lang, max_septets=max_septets)
                return _reply(
                    txt,
                    "CORRECTION",
                    declared,
                    transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
                    max_septets=max_septets,
                )

            state["step"] = "correction_amount"
            state["in_correction"] = True
            txt, declared = render_phrase("ask_new_amount", lang, max_septets=max_septets)
            return _reply(
                txt,
                "CORRECTION",
                declared,
                transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
                max_septets=max_septets,
            )

        txt, declared = render_phrase("confirm_prompt_retry", lang, max_septets=max_septets)
        return _reply(
            txt,
            "CLARIFICATION_NEEDED",
            declared,
            transaction={"id": state.get("reference"), "status": "pending"} if state.get("reference") else None,
            max_septets=max_septets,
        )

    if step == "correction_beneficiary":
        if kw_intent == "CANCEL" or _norm(text) == "sumua":
            return _cancel_pending_reply(state, bank, lang, max_septets, dry_run=dry_run)
        state["in_correction"] = True
        err_or_clarify = _resolve_beneficiary_or_clarify(
            state, text, phone, bank, lang, max_septets,
            ask_phrase_key="ask_new_beneficiary", fallback_step="correction_beneficiary",
        )
        if err_or_clarify:
            return err_or_clarify
        return _create_pending_operation(state, phone, bank, lang, "CORRECTION", max_septets, dry_run=dry_run)

    if step == "correction_amount":
        if kw_intent == "CANCEL" or _norm(text) == "sumua":
            return _cancel_pending_reply(state, bank, lang, max_septets, dry_run=dry_run)
        new_amt = parse_amount(text)
        if new_amt:
            return _apply_amount_correction(state, new_amt, phone, bank, lang, max_septets, dry_run=dry_run)
        # Permet aussi de modifier le bénéficiaire (ex. taper "Brenda" après avoir choisi "3. Modifier")
        if state.get("op_type", "transfer") == "transfer" and len(text.strip()) >= 2:
            state["in_correction"] = True
            err_or_clarify = _resolve_beneficiary_or_clarify(
                state, text, phone, bank, lang, max_septets,
                ask_phrase_key="ask_new_beneficiary", fallback_step="correction_beneficiary",
            )
            if err_or_clarify:
                return err_or_clarify
            return _create_pending_operation(state, phone, bank, lang, "CORRECTION", max_septets, dry_run=dry_run)
        txt, declared = render_phrase("invalid_amount", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    # ── Choix bénéficiaire homonyme ──
    if step == "transfer_pick_benef":
        if kw_intent == "CANCEL" and state.get("reference"):
            return _cancel_pending_reply(state, bank, lang, max_septets, dry_run=dry_run)
        cands = state.get("candidates") or []
        chosen: dict[str, Any] | None = None
        if text.isdigit() and 1 <= int(text) <= len(cands):
            chosen = cands[int(text) - 1]
        else:
            # Permet aussi de saisir le nom ou le numéro exact d'un des candidats proposés
            parsed_p = parse_phone(text)
            if parsed_p:
                p_matches = [c for c in cands if _local_phone(c.get("phone")) == _local_phone(parsed_p)]
                if len(p_matches) == 1:
                    chosen = p_matches[0]
            elif len(_norm(text)) >= 2:
                q_toks = _norm(text).split()
                n_matches = [c for c in cands if all(t in _norm(c.get("name")) for t in q_toks)]
                if len(n_matches) == 1:
                    chosen = n_matches[0]

        if chosen is not None:
            state["to"] = chosen.get("phone")
            state["to_name"] = chosen.get("name") or _local_phone(chosen.get("phone"))
            state.pop("candidates", None)
            if state.get("amount"):
                out_intent = "CORRECTION" if state.get("in_correction") else "TRANSFER"
                return _create_pending_operation(state, phone, bank, lang, out_intent, max_septets, dry_run=dry_run)
            state["step"] = "transfer_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"beneficiary": state["to_name"]}, max_septets=max_septets)

        txt, declared, shown = _format_candidates(cands, lang, max_septets)
        state["candidates"] = shown
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    # ── Étapes Transfert ──
    if step == "transfer_to":
        # Si l'utilisateur saisit "Paul 5000" ou "621028428 5000", capture aussi le montant
        if not state.get("amount"):
            maybe_amt = parse_amount(text)
            has_benef_part = bool(parse_phone(text) or _clean_beneficiary_query(text))
            if maybe_amt and has_benef_part:
                state["amount"] = maybe_amt
        err_or_clarify = _resolve_beneficiary_or_clarify(state, text, phone, bank, lang, max_septets)
        if err_or_clarify:
            return err_or_clarify
        if state.get("amount"):
            return _create_pending_operation(state, phone, bank, lang, "TRANSFER", max_septets, dry_run=dry_run)
        state["step"] = "transfer_amount"
        txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"beneficiary": state.get("to_name")}, max_septets=max_septets)

    if step == "transfer_amount":
        amt = parse_amount(text)
        if not amt:
            txt, declared = render_phrase("invalid_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["amount"] = amt
        return _create_pending_operation(state, phone, bank, lang, "TRANSFER", max_septets, dry_run=dry_run)

    # ── Étape Calcul de Frais ──
    if step == "fee_amount":
        amt = parse_amount(text)
        if not amt:
            txt, declared = render_phrase("invalid_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        if dry_run:
            state["step"] = "menu"
            return _reply("", "FEE_INQUIRY", resolve_lang(lang), end=True, max_septets=max_septets)
        kind = state.get("fee_kind") or _detect_fee_kind(text)
        return _do_fees(amt, bank, lang, max_septets, kind=kind)

    # ── Étapes Crédit (Airtime) ──
    if step == "airtime_target":
        if text == "1":
            state["to"] = phone
            state["op_type"] = "airtime"
            if state.get("amount"):
                return _create_pending_operation(state, phone, bank, lang, "AIRTIME_PURCHASE", max_septets, dry_run=dry_run)
            state["step"] = "airtime_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"to": phone}, max_septets=max_septets)
        if text == "2":
            state["step"] = "airtime_phone"
            txt, declared = render_phrase("ask_airtime_phone", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        p = parse_phone(text)
        if p:
            state["to"] = p
            state["op_type"] = "airtime"
            maybe_amt = parse_amount(text)
            if maybe_amt:
                state["amount"] = maybe_amt
            if state.get("amount"):
                return _create_pending_operation(state, phone, bank, lang, "AIRTIME_PURCHASE", max_septets, dry_run=dry_run)
            state["step"] = "airtime_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"to": p}, max_septets=max_septets)
        txt, declared = render_phrase("ask_airtime_target", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    if step == "airtime_phone":
        p = parse_phone(text)
        if not p:
            txt, declared = render_phrase("invalid_phone", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["to"] = p
        state["op_type"] = "airtime"
        maybe_amt = parse_amount(text)
        if maybe_amt:
            state["amount"] = maybe_amt
        if state.get("amount"):
            return _create_pending_operation(state, phone, bank, lang, "AIRTIME_PURCHASE", max_septets, dry_run=dry_run)
        state["step"] = "airtime_amount"
        txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"to": p}, max_septets=max_septets)

    if step == "airtime_amount":
        amt = parse_amount(text)
        if not amt:
            txt, declared = render_phrase("invalid_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["amount"] = amt
        state["op_type"] = "airtime"
        return _create_pending_operation(state, phone, bank, lang, "AIRTIME_PURCHASE", max_septets, dry_run=dry_run)

    # ── Étapes Factures ──
    if step == "bill_pick":
        biller_map = {"1": "ENEO", "2": "CAMWATER", "3": "CANAL", "4": "CAMTEL"}
        biller = biller_map.get(text) or detect_biller(text)
        if not biller:
            txt, declared = render_phrase("ask_biller", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["biller"] = biller
        state["op_type"] = "bill"
        maybe_amt = None if text in biller_map else parse_amount(text)
        if maybe_amt:
            state["amount"] = maybe_amt
        if state.get("amount"):
            return _create_pending_operation(state, phone, bank, lang, "BILL_PAYMENT", max_septets, dry_run=dry_run)
        state["step"] = "bill_amount"
        txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"biller": biller}, max_septets=max_septets)

    if step == "bill_amount":
        amt = parse_amount(text)
        if not amt:
            txt, declared = render_phrase("invalid_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["amount"] = amt
        state["op_type"] = "bill"
        return _create_pending_operation(state, phone, bank, lang, "BILL_PAYMENT", max_septets, dry_run=dry_run)

    # ── Étape Terminologie ──
    if step == "term_pick":
        tmap = {"1": "fee", "2": "limit", "3": "beneficiary"}
        term_key = tmap.get(text) or detect_term_question(text)
        if not term_key:
            txt, declared = render_phrase("ask_term", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        txt, declared = render_phrase(f"term_{term_key}", lang, max_septets=max_septets)
        return _reply(txt, "TERM_EXPLANATION", declared, parameters={"term": term_key}, end=True, max_septets=max_septets)

    # ── Menu principal ou commande directe en langage naturel (Ewondo / Duala / FR / EN) ──
    if text == "1" or kw_intent == "BALANCE_INQUIRY":
        if dry_run:
            state["step"] = "menu"
            return _reply("", "BALANCE_INQUIRY", resolve_lang(lang), end=True, max_septets=max_septets)
        return _do_balance(phone, bank, lang, max_septets)

    if text == "2" or kw_intent == "TRANSFER":
        _clear_op_state(state)
        state["op_type"] = "transfer"
        amt = None if text == "2" else parse_amount(text)
        if amt:
            state["amount"] = amt
        if text != "2":
            err_or_clarify = _resolve_beneficiary_or_clarify(state, text, phone, bank, lang, max_septets)
            if err_or_clarify:
                return err_or_clarify
            if state.get("amount"):
                return _create_pending_operation(state, phone, bank, lang, "TRANSFER", max_septets, dry_run=dry_run)
            state["step"] = "transfer_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"beneficiary": state.get("to_name")}, max_septets=max_septets)
        state["step"] = "transfer_to"
        txt, declared = render_phrase("ask_transfer_to", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    if text == "3" or kw_intent == "FEE_INQUIRY":
        _clear_op_state(state)
        fee_kind = "transfer" if text == "3" else _detect_fee_kind(text)
        amt = None if text == "3" else parse_amount(text)
        if amt:
            if dry_run:
                state["step"] = "menu"
                return _reply("", "FEE_INQUIRY", resolve_lang(lang), end=True, max_septets=max_septets)
            return _do_fees(amt, bank, lang, max_septets, kind=fee_kind)
        state["fee_kind"] = fee_kind
        state["step"] = "fee_amount"
        txt, declared = render_phrase("ask_fee_amount", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    if text == "4" or kw_intent == "TRANSACTION_HISTORY":
        if dry_run:
            state["step"] = "menu"
            return _reply("", "TRANSACTION_HISTORY", resolve_lang(lang), end=True, max_septets=max_septets)
        return _do_history(phone, bank, lang, max_septets)

    if text == "5" or kw_intent == "AIRTIME_PURCHASE":
        _clear_op_state(state)
        state["op_type"] = "airtime"
        amt = None if text == "5" else parse_amount(text)
        target_p = None if text == "5" else parse_phone(text)
        if amt:
            state["amount"] = amt
        if target_p:
            state["to"] = target_p
        if amt and target_p:
            return _create_pending_operation(state, phone, bank, lang, "AIRTIME_PURCHASE", max_septets, dry_run=dry_run)
        if target_p:
            state["step"] = "airtime_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"to": target_p}, max_septets=max_septets)
        state["step"] = "airtime_target"
        txt, declared = render_phrase("ask_airtime_target", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    if text == "6" or kw_intent == "BILL_PAYMENT":
        _clear_op_state(state)
        state["op_type"] = "bill"
        biller = None if text == "6" else detect_biller(text)
        amt = None if text == "6" else parse_amount(text)
        if biller:
            state["biller"] = biller
        if amt:
            state["amount"] = amt
        if biller and amt:
            return _create_pending_operation(state, phone, bank, lang, "BILL_PAYMENT", max_septets, dry_run=dry_run)
        if biller:
            state["step"] = "bill_amount"
            txt, declared = render_phrase("ask_amount", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, parameters={"biller": biller}, max_septets=max_septets)
        state["step"] = "bill_pick"
        txt, declared = render_phrase("ask_biller", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    if text == "7":
        _clear_op_state(state)
        state["step"] = "term_pick"
        txt, declared = render_phrase("ask_term", lang, max_septets=max_septets)
        return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)

    # Canal ATM : retrait en multiples de 5 000 FCFA
    if channel == "atm" or kw_intent == "WITHDRAWAL":
        _clear_op_state(state)
        amt = parse_amount(text)
        if not amt or amt % 5000 != 0:
            txt, declared = render_phrase("atm_multiple", lang, max_septets=max_septets)
            return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
        state["op_type"] = "withdrawal"
        state["amount"] = amt
        return _create_pending_operation(state, phone, bank, lang, "TRANSFER", max_septets, dry_run=dry_run)

    state["step"] = "menu"
    txt, declared = render_phrase("menu", lang, max_septets=max_septets)
    return _reply(txt, "CLARIFICATION_NEEDED", declared, max_septets=max_septets)
