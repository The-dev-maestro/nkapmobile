from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.core.contracts import ScreenContext, ScreenNode


def _norm(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFD", (value or "").lower())
    text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


class AppPlaybookStore:
    """
    Charge les fiches de connaissance applicative M5 (`cerveau/m5_kb/<app>/playbook.json`).
    Permet au harnais (malgré un LLM local 1.5B) de connaître le fonctionnement exact
    de chaque écran de l'environnement de test SAFINUM, de Wave et d'Orange Max it.
    """

    def __init__(self, kb_root: str | Path):
        self.root = Path(kb_root)
        self.playbooks: list[dict[str, Any]] = []
        self._load_all()

    def _load_all(self) -> None:
        self.playbooks = []
        if not self.root.exists():
            return
        for pb_path in sorted(self.root.glob("*/playbook.json")):
            try:
                data = json.loads(pb_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("app_id"):
                    self.playbooks.append(data)
            except Exception:
                continue

    def detect_playbook(self, screen_context: ScreenContext) -> dict[str, Any] | None:
        pkg = (screen_context.app.package if screen_context.app else "").lower()
        url = (screen_context.page.url if screen_context.page else "").lower()
        corpus = _norm(" ".join((n.text or "") + " " + (n.content_desc or "") for n in screen_context.nodes[:80]))

        for pb in self.playbooks:
            for p in pb.get("match_packages", []):
                if p and p.lower() in pkg:
                    return pb
            for u in pb.get("match_urls", []):
                if u and u.lower() in url:
                    return pb

        for pb in self.playbooks:
            cues = pb.get("match_text_cues", [])
            if any(_norm(c) in corpus for c in cues if c):
                return pb
        return None

    def infer_screen_key(self, pb: dict[str, Any], screen_context: ScreenContext) -> str:
        url = (screen_context.page.url if screen_context.page else "").lower()
        hint = _norm(screen_context.screen_hint)
        corpus = _norm(" ".join((n.text or "") for n in screen_context.nodes[:80]))

        if pb.get("app_id") == "safinum-sandbox":
            if "/receipt" in url or any(k in corpus for k in ("operation reussie", "mvet o boban mben", "ebolo e tilabe na bwam", "nouveau solde")):
                return "receipt"
            if "/review" in url or "/recap" in url or any(k in corpus for k in ("verifiez avant de confirmer", "fombo ossussua", "ombwa oboso ba bamse")):
                return "review"
            if "/transfer" in url or any(k in corpus for k in ("mes beneficiaires", "bot bam ba non moni", "bakusa bam", "nombo telefon nge dzoe", "jusqu'a 500 000", "akui 500 000")):
                return "transfer"
            if "/pay" in url or any(k in corpus for k in ("choisir le service", "tob isae", "operateur telephone", "nsaa telefon")):
                return "pay"
            if "/history" in url or any(k in corpus for k in ("historique des operations", "itang mvet")):
                return "history"
            if hint in pb.get("screen_guides", {}):
                return hint
            return "home"

        if hint in pb.get("screen_guides", {}):
            return hint
        return "home"

    @staticmethod
    def is_screen_guide_question(q_norm: str) -> bool:
        cues = (
            "je dois faire quoi",
            "que dois-je faire",
            "que dois je faire",
            "quoi faire ici",
            "faire quoi ici",
            "fais quoi ici",
            "je fais quoi",
            "comment faire ici",
            "explique-moi cet ecran",
            "explique moi cet ecran",
            "explique cet ecran",
            "a quoi sert cet ecran",
            "c'est quoi cet ecran",
            "cest quoi cet ecran",
            "je suis perdu",
            "je suis bloque",
            "comment remplir",
            "comment utiliser cet ecran",
            "comment ca marche ici",
            "aide-moi ici",
            "aide moi ici",
        )
        return any(c in q_norm for c in cues)

    @staticmethod
    def find_matching_node(
        nodes: list[ScreenNode],
        patterns: list[str],
        prefer_button: bool = False,
    ) -> ScreenNode | None:
        if not patterns:
            return None
        norm_pats = [_norm(p) for p in patterns if p]
        candidates: list[tuple[int, ScreenNode]] = []
        for n in nodes:
            txt_n = _norm(n.text or n.content_desc)
            if not txt_n:
                continue
            for p in norm_pats:
                if txt_n == p:
                    score = 100 + (20 if (prefer_button and (n.clickable or n.tag in {"button", "a"})) else 0)
                    candidates.append((score, n))
                    break
                if p in txt_n and len(txt_n) <= len(p) + 28:
                    score = 60 + (15 if (prefer_button and (n.clickable or n.tag in {"button", "a"})) else 0)
                    candidates.append((score, n))
                    break
        if not candidates:
            return None
        candidates.sort(key=lambda pair: (-pair[0], pair[1].bounds[1] if len(pair[1].bounds) == 4 else 9999))
        return candidates[0][1]

    def match_qa_shortcut(
        self,
        pb: dict[str, Any],
        screen_key: str,
        q_norm: str,
    ) -> dict[str, Any] | None:
        for sc in pb.get("qa_shortcuts", []):
            allowed_screens = sc.get("screens")
            if allowed_screens and screen_key not in allowed_screens:
                continue
            triggers = sc.get("triggers", [])
            if any(_norm(t) in q_norm for t in triggers if t):
                return sc
        return None
