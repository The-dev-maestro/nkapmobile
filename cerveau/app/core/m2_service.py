from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.core.contracts import (
    ActionMessage,
    ActionPayload,
    ActionTarget,
    NotebookLine,
    ScreenContext,
    ScreenNode,
    Transcript,
)
from app.core.validators import extract_amounts, text_is_covered, validate_action_stream
from app.llm import LLMAdapter


JURY_DRAWER_EXCLUDES = [
    "declencher une erreur",
    "outil interne safinum",
    "injecter du contenu",
    "modifier les valeurs canoniques",
    "environnement de test",
    "protocole de test",
    "retour au hackathon",
]

LOCAL_LANG_TO_FR: dict[str, str] = {
    # ── En-tête & Étapes (Douala + Ewondo -> Français pur) ──
    "ndabo a moni o myooo": "Banque en ligne",
    "ndabo a moni o mycco": "Banque en ligne",
    "nda moni a nkul": "Banque en ligne",
    "konto ango": "Votre compte",
    "bol yi": "Votre compte",
    "konto ya pondi": "Compte courant",
    "bol a melu": "Compte courant",
    "moni ma pene": "Solde disponible",
    "nden wog i bol": "Solde disponible",
    "moni ma dia": "Solde",
    "nden": "Solde",
    "mabala": "Frais",
    "mbug": "Frais",
    "mukusa": "Bénéficiaire",
    "nyi a non": "Bénéficiaire",
    "botali": "Récapitulatif",
    "ntolan": "Récapitulatif",
    "bola la mbale": "Confirmation",
    "yemban": "Confirmation",
    # ── Écran 1 : Accueil / Solde ──
    "nimero a konto": "Numéro de compte",
    "nem bol": "Numéro de compte",
    "loma moni": "Effectuer un transfert",
    "to nden": "Effectuer un transfert",
    "ombwa mabala": "Consulter les frais",
    "ne mbug": "Consulter les frais",
    "ombwa moni mango pe loma moni na musango.": "Consultez votre solde et lancez un transfert en toute sécurité.",
    "nyi bol ni nden, to wo le.": "Consultez votre solde et lancez un transfert en toute sécurité.",
    "bebolo ba sukan": "Transactions récentes",
    "mimboan mi ndon": "Transactions récentes",
    "sawedi la mome-nyunga": "Paiement marchand",
    "yanan nkukum": "Paiement marchand",
    "musawedi mukusabe": "Salaire reçu",
    "moni esae": "Salaire reçu",
    "moni malomabe": "Transfert reçu",
    "nden a non": "Transfert reçu",
    "kalati a weya": "Facture d'électricité",
    "kalara ndok": "Facture d'électricité",
    "musango": "Sécurité",
    "mvo'e": "Sécurité",
    "ombwa bwam dina na nimero ya mukusa oboso ba bola loma.": "Vérifiez toujours le nom et le numéro du bénéficiaire avant de confirmer un transfert.",
    "fombok eyolo ai nombo obusu.": "Vérifiez toujours le nom et le numéro du bénéficiaire avant de confirmer un transfert.",
    "diwuta la musango": "Connexion sécurisée",
    "ntilan mvo'e": "Connexion sécurisée",
    # ── Écran 2 : Frais de transfert ──
    "mabala ma loma": "Frais de transfert",
    "mbug i nden": "Frais de transfert",
    "pona njika loma na mytango. mabala mabolan muso.": "Choisissez le type de transfert et le montant. Les frais sont calculés automatiquement.",
    "lo mvet nden, mbug a owon le.": "Choisissez le type de transfert et le montant. Les frais sont calculés automatiquement.",
    "njika ebolo": "Type d'opération",
    "mvet": "Type d'opération",
    "konto safinum": "Compte Safinum",
    "bol safinum": "Compte Safinum",
    "loma la dibokimene pe musawedi te": "Transfert instantané et gratuit",
    "nden nele, o mbug le": "Transfert instantané et gratuit",
    "loma la pondi": "Transfert standard",
    "nden ya melu": "Transfert standard",
    "loma la ponda": "Transfert express",
    "nden avol": "Transfert express",
    "moni ma loma": "Montant à envoyer",
    "nden to": "Montant à envoyer",
    "bonam": "Gratuit",
    "zeze": "Gratuit",
    "botali ba busa": "Total à débiter",
    "ntolan wog": "Total à débiter",
    "moni ma dia ombusa": "Solde après opération",
    "nden wog i bol a mvet": "Solde après opération",
    "ala oboso": "Continuer",
    "kele obusu": "Continuer",
    "timba": "Retour",
    "bulan": "Retour",
    # ── Écran 3 : Bénéficiaire ──
    "tila myango ma mukusa. ombwa nimero oboso ba bola.": "Renseignez les informations du destinataire. Vérifiez toujours le numéro avant de valider.",
    "bol nem a lon, elee ke.": "Renseignez les informations du destinataire. Vérifiez toujours le numéro avant de valider.",
    "nu mukusa a si bolane o konto. ombwa nimero oboso ba ala.": "Ce bénéficiaire n'a jamais été utilisé sur ce compte. Vérifiez le numéro avant de continuer.",
    "nyi nyo a ngenan tekeulan. fombok nombo.": "Ce bénéficiaire n'a jamais été utilisé sur ce compte. Vérifiez le numéro avant de continuer.",
    "dina la mukusa": "Nom du bénéficiaire",
    "nem a nyi": "Nom du bénéficiaire",
    "nimero a telefone": "Numéro de téléphone",
    "nem telefon": "Numéro de téléphone",
    "njom a loma": "Motif du transfert",
    "son nden": "Motif du transfert",
    "mwendi (o tondi te)": "Note (optionnel)",
    "efia": "Note (optionnel)",
    "na ombwe dina na nimero ya mukusa.": "J'ai vérifié le nom et le numéro du bénéficiaire.",
    "nele nem a nyi.": "J'ai vérifié le nom et le numéro du bénéficiaire.",
    "paiement de services": "Paiement de services",
    "soutien familial": "Soutien familial",
    # ── Écran 4 & 5 : Récapitulatif & Reçu ──
    "ombwa myango mese oboso ba bola loma.": "Vérifiez les informations avant de confirmer le transfert.",
    "elee ke, zo bol.": "Vérifiez les informations avant de confirmer le transfert.",
    "moni": "Montant",
    "botali busabe": "Total débité",
    "telefone": "Téléphone",
    "telefon": "Téléphone",
    "edun": "Référence",
    "nombo ndem": "Référence",
    "ebolo": "Opération",
    "njom": "Motif",
    "son": "Motif",
    "na bamse na myango ma tenge.": "Je confirme que les informations ci-dessus sont correctes.",
    "me yemban na mam mese me ne mben.": "Je confirme que les informations ci-dessus sont correctes.",
    "tukwa": "Modifier",
    "tyende": "Modifier",
    "bamse loma": "Confirmer le transfert",
    "yemban nden": "Confirmer le transfert",
    "loma dibamsebe": "Transfert confirmé",
    "nden e keya": "Transfert confirmé",
    "ebolo ango e tilabe na bwam.": "Votre opération a été enregistrée avec succès.",
    "mvet wog o tiliban mben.": "Votre opération a été enregistrée avec succès.",
    "moni ma pene ma dia": "Nouveau solde disponible",
    "nden mfefe i bol": "Nouveau solde disponible",
    "loma dipepe": "Nouveau transfert",
    "nden mfefe": "Nouveau transfert",
    "timba o bekombo": "Retour à l'accueil",
    "bulan a nda": "Retour à l'accueil",
    # ── Bannières d'erreurs & Sécurité ──
    "njom e bodi": "Une erreur est survenue",
    "ekop e kuiya": "Une erreur est survenue",
    "moni ma si kolisane o bola loma.": "Solde insuffisant pour effectuer ce transfert.",
    "nden og bol, o sok le.": "Solde insuffisant pour effectuer ce transfert.",
    "moni ma si kolisane": "Solde insuffisant",
    "nden og bol": "Solde insuffisant",
    "bediedi ba musango": "Alerte de sécurité",
    "mebende m'ekali": "Alerte de sécurité",
    "bediedi ba musango : ombwa nimero ya mukusa oboso ba ala.": "Alerte de sécurité : vérifiez le numéro du bénéficiaire avant de continuer.",
    "ombwa nimero ya mukusa oboso ba ala.": "Vérifiez le numéro du bénéficiaire avant de continuer.",
    "bege nem telefon mot o besu.": "Vérifiez le numéro du bénéficiaire avant de continuer.",
    "o si langwea moto kode ango ya dimbambe.": "Ne partagez jamais votre code secret. Un agent ne vous le demandera pas.",
    "te ve mot kode wog ya nsolan.": "Ne partagez jamais votre code secret. Un agent ne vous le demandera pas.",
    "njom a singi": "Erreur réseau",
    "evudu a nsingi": "Erreur réseau",
    "njom a singi : kekise pene.": "Erreur réseau : le service est temporairement indisponible. Réessayez.",
    "ebolo e si ma-babe tatan. kekise pene.": "Le service est temporairement indisponible. Réessayez.",
    "isae e se ben. lo ko.": "Le service est temporairement indisponible. Réessayez.",
    "mwendi ma mwena": "Message important",
    "efia e ne mfi": "Message important",
}
DOUALA_FR_GLOSSES = LOCAL_LANG_TO_FR

ALLOWED_HIGHLIGHT_STYLES = {"box", "circle", "frame", "underline"}
ALLOWED_COLORS = {"ink", "yellow", "red", "green"}


class KnowledgeBase:
    """Gestionnaire de la base de connaissances M5 locale."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._stores: dict[str, dict] = {}
        self.default_company = "demo-fintech"
        self._load_company(self.default_company)

    def _load_company(self, company_id: str) -> dict:
        if company_id in self._stores:
            return self._stores[company_id]

        company_dir = self.root / company_id
        if not company_dir.exists():
            company_dir = self.root / self.default_company

        manifest_path = company_dir / "manifest.json"
        lexicon_path = company_dir / "lexicon.json"
        phrases_path = company_dir / "phrases.json"
        ui_inv_path = company_dir / "ui_inventory.json"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        lexicon = json.loads(lexicon_path.read_text(encoding="utf-8")) if lexicon_path.exists() else {}
        phrases = json.loads(phrases_path.read_text(encoding="utf-8")) if phrases_path.exists() else {}
        ui_inventory = json.loads(ui_inv_path.read_text(encoding="utf-8")) if ui_inv_path.exists() else {}

        store = {
            "manifest": manifest,
            "lexicon": lexicon,
            "phrases": phrases,
            "ui_inventory": ui_inventory,
        }
        self._stores[company_id] = store
        return store

    def get_store(self, company_id: str | None = None) -> dict:
        cid = company_id or self.default_company
        return self._load_company(cid)

    @property
    def terms(self) -> list[str]:
        """Retourne l'ensemble des termes lexiques et gabarits connus."""
        store = self.get_store()
        lexicon = store.get("lexicon", {})
        phrases = store.get("phrases", {})

        phrase_words: list[str] = []
        for p_data in phrases.values():
            if isinstance(p_data, dict):
                for text in p_data.values():
                    cleaned = re.sub(r"\{[^}]+\}", "", text)
                    phrase_words.extend(cleaned.split())

        all_terms = [*lexicon.keys(), *lexicon.values(), *phrase_words]
        return list(set(all_terms))

    def get_phrase(self, key: str, lang: str = "ewo", company_id: str | None = None) -> str | None:
        store = self.get_store(company_id)
        phrases = store.get("phrases", {})
        phrase_entry = phrases.get(key, {})
        if isinstance(phrase_entry, dict):
            return phrase_entry.get(lang) or phrase_entry.get("fr")
        return None


class _StreamBuilder:
    """Construit proprement un flux ActionMessage ordonné et séquentiel."""

    def __init__(self, transcript: Transcript, base_ts: int):
        self.transcript = transcript
        self.base_ts = base_ts
        self.actions: list[ActionMessage] = []
        self._seq = 0

    def add(self, run_after_ms: int, payload: ActionPayload) -> None:
        self._seq += 1
        self.actions.append(
            ActionMessage(
                type="action",
                session_id=self.transcript.session_id,
                turn_id=self.transcript.turn_id,
                ts=self.base_ts + run_after_ms,
                seq=self._seq,
                speak_seg=0,
                run_after_ms=run_after_ms,
                action=payload,
            )
        )

    def speak(self, phrase_key: str, text: str, lang: str, run_after_ms: int = 0) -> None:
        self.add(
            run_after_ms,
            ActionPayload(
                t="speak",
                id=f"spk_{self._seq + 1}",
                text=text,
                lang=lang,
                mode="bank",
                phrase_key=phrase_key,
            ),
        )

    def draw(
        self,
        t: str,
        mark_id: str,
        target_id: str,
        *,
        color: str = "ink",
        duration_ms: int = 620,
        run_after_ms: int = 0,
        label: str | None = None,
    ) -> None:
        self.add(
            run_after_ms,
            ActionPayload(
                t=t,  # type: ignore[arg-type]
                id=mark_id,
                target=ActionTarget(node_id=target_id),
                color=color,
                duration_ms=duration_ms,
                label=label,
            ),
        )

    def arrow(
        self,
        mark_id: str,
        from_id: str,
        to_id: str,
        *,
        color: str = "ink",
        duration_ms: int = 620,
        run_after_ms: int = 0,
    ) -> None:
        self.add(
            run_after_ms,
            ActionPayload(
                t="arrow",
                id=mark_id,
                from_=ActionTarget(node_id=from_id),
                to=ActionTarget(node_id=to_id),
                color=color,
                duration_ms=duration_ms,
            ),
        )

    def notebook(
        self,
        nb_id: str,
        title: str,
        lines: list[NotebookLine],
        anchor_id: str | None = None,
        run_after_ms: int = 0,
    ) -> None:
        self.add(
            run_after_ms,
            ActionPayload(
                t="notebook",
                id=nb_id,
                title=title,
                anchor=ActionTarget(node_id=anchor_id) if anchor_id else None,
                lines=lines,
            ),
        )

    def write(
        self,
        mark_id: str,
        text: str,
        target_id: str,
        *,
        dy: int = -66,
        size: int = 27,
        per_letter_ms: int = 55,
        run_after_ms: int = 900,
    ) -> None:
        self.add(
            run_after_ms,
            ActionPayload(
                t="write",
                id=mark_id,
                text=text,
                target=ActionTarget(node_id=target_id, dy=dy),
                size=size,
                color="ink",
                backing="paper",
                per_letter_ms=per_letter_ms,
            ),
        )

    def clear(self, run_after_ms: int = 8000) -> None:
        self.add(run_after_ms, ActionPayload(t="clear"))


class M2Service:
    """Cerveau M2 piloté dynamiquement par LLM open-weight + harnais de sécurité."""

    def __init__(self, kb_root: str | Path, llm: LLMAdapter | None = None):
        self.kb = KnowledgeBase(kb_root)
        self.llm = llm or LLMAdapter()
        self.last_screen_context: ScreenContext | None = None
        self._turn_cache: dict[tuple[int, str, str], list[ActionMessage]] = {}

    @staticmethod
    def _norm(value: str | None) -> str:
        decomposed = unicodedata.normalize("NFD", (value or "").lower())
        text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
        for src, dst in (
            ("ɔ", "o"),
            ("ɛ", "e"),
            ("ŋ", "n"),
            ("а", "a"),
            ("е", "e"),
            ("о", "o"),
            ("р", "p"),
            ("с", "c"),
            ("у", "y"),
            ("х", "x"),
            ("м", "m"),
            ("т", "t"),
            ("к", "k"),
        ):
            text = text.replace(src, dst)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _enforce_tutoiement(text: str) -> str:
        """Transforme les formes résiduelles en « vous/votre » vers un tutoiement chaleureux HeyClicky."""
        out = (text or "").strip()
        if not out:
            return ""
        replacements = (
            (r"\bVous pouvez\b", "Tu peux"),
            (r"\bvous pouvez\b", "tu peux"),
            (r"\bVous devez\b", "Tu dois"),
            (r"\bvous devez\b", "tu dois"),
            (r"\bVous allez\b", "Tu vas"),
            (r"\bvous allez\b", "tu vas"),
            (r"\bVous avez\b", "Tu as"),
            (r"\bvous avez\b", "tu as"),
            (r"\bVous êtes\b", "Tu es"),
            (r"\bvous êtes\b", "tu es"),
            (r"\bVotre\b", "Ton"),
            (r"\bvotre\b", "ton"),
            (r"\bVos\b", "Tes"),
            (r"\bvos\b", "tes"),
            (r"\bVous\b", "Toi"),
            (r"\bvous\b", "toi"),
            (r"\bN'oubliez pas\b", "N'oublie pas"),
            (r"\bn'oubliez pas\b", "n'oublie pas"),
            (r"\bVérifiez\b", "Vérifie"),
            (r"\bvérifiez\b", "vérifie"),
            (r"\bInspectez\b", "Inspecte"),
            (r"\binspectez\b", "inspecte"),
            (r"\bExaminez\b", "Examine"),
            (r"\bexaminez\b", "examine"),
            (r"\bAppuyez\b", "Appuie"),
            (r"\bappuyez\b", "appuie"),
            (r"\bCliquez\b", "Clique"),
            (r"\bcliquez\b", "clique"),
            (r"\bCochez\b", "Coche"),
            (r"\bcochez\b", "coche"),
            (r"\bRelisez\b", "Relis"),
            (r"\brelisez\b", "relis"),
            (r"\bConsultez\b", "Consulte"),
            (r"\bconsultez\b", "consulte"),
            (r"\bRegardez\b", "Regarde"),
            (r"\bregardez\b", "regarde"),
            (r"\bConfirmez\b", "Confirme"),
            (r"\bconfirmez\b", "confirme"),
            (r"\bPatientez\b", "Patiente"),
            (r"\bpatientez\b", "patiente"),
            (r"\bRéessayez\b", "Réessaie"),
            (r"\bréessayez\b", "réessaie"),
            (r"\bChoisissez\b", "Choisis"),
            (r"\bchoisissez\b", "choisis"),
            (r"\bRenseignez\b", "Renseigne"),
            (r"\brenseignez\b", "renseigne"),
            (r"\bContrôlez\b", "Contrôle"),
            (r"\bcontrôlez\b", "contrôle"),
            (r"\bAssurez-vous\b", "Assure-toi"),
            (r"\bassurez-vous\b", "assure-toi"),
            (r"\bSuivez\b", "Suis"),
            (r"\bsuivez\b", "suis"),
            (r"\bEnvoyez\b", "Envoie"),
            (r"\benvoyez\b", "envoie"),
            (r"\bPrenez\b", "Prends"),
            (r"\bprenez\b", "prends"),
            (r"\bUtilisez\b", "Utilise"),
            (r"\butilisez\b", "utilise"),
            (r"\bEntrez\b", "Entre"),
            (r"\bentrez\b", "entre"),
            (r"\bTapez\b", "Tape"),
            (r"\btapez\b", "tape"),
            (r"\bSélectionnez\b", "Sélectionne"),
            (r"\bsélectionnez\b", "sélectionne"),
            (r"\bVous verrez\b", "Tu verras"),
            (r"\bvous verrez\b", "tu verras"),
            (r"\bTu vérifie\b", "Tu vérifies"),
            (r"\btu vérifie\b", "tu vérifies"),
            (r"\bTu confirme\b", "Tu confirmes"),
            (r"\btu confirme\b", "tu confirmes"),
            (r"\bTu continue\b", "Tu continues"),
            (r"\btu continue\b", "tu continues"),
        )
        for pat, rep in replacements:
            out = re.sub(pat, rep, out)
        # "ton" devant nom féminin courant -> "ta"
        out = re.sub(r"\bTon (information|application|opération|carte|case|référence|sécurité|attention|banque)\b", r"Ta \1", out)
        out = re.sub(r"\bton (information|application|opération|carte|case|référence|sécurité|attention|banque)\b", r"ta \1", out)
        # Empêche le LLM de parler à la 1re personne pour les données bancaires de l'utilisateur ("Mes dernières transactions", "Mon solde")
        user_assets = r"(dernières?\s+transactions?|transactions?|opérations?|paiements?|transferts?|soldes?|comptes?|frais|bénéficiaires?|numéros?)"
        out = re.sub(rf"\bMes\s+{user_assets}\b", r"Tes \1", out)
        out = re.sub(rf"\bmes\s+{user_assets}\b", r"tes \1", out)
        out = re.sub(rf"\bMon\s+{user_assets}\b", r"Ton \1", out)
        out = re.sub(rf"\bmon\s+{user_assets}\b", r"ton \1", out)
        out = re.sub(rf"\bMa\s+(dernière\s+transaction|transaction|dernière\s+opération|liste)\b", r"Ta \1", out)
        out = re.sub(rf"\bma\s+(dernière\s+transaction|transaction|dernière\s+opération|liste)\b", r"ta \1", out)
        # Corrections fréquentes de genre du modèle 1.5B
        out = re.sub(r"\bunes?\s+retransfert\b", "un transfert", out, flags=re.IGNORECASE)
        out = re.sub(r"\bun\s+retransfert\b", "un transfert", out, flags=re.IGNORECASE)
        out = re.sub(r"\bla\s+récapitulatif\b", "le récapitulatif", out, flags=re.IGNORECASE)
        return out

    @staticmethod
    def _sanitize_ordinals(text: str) -> str:
        """Remplace les ordinaux chiffrés ('1er', '2ème') qui ne sont pas des montants d'écran."""
        out = (text or "").strip()
        if not out:
            return ""
        out = re.sub(r"\b1er\b", "premier", out, flags=re.IGNORECASE)
        out = re.sub(r"\b1ère\b", "première", out, flags=re.IGNORECASE)
        out = re.sub(r"\b2(?:e|ème)\b", "deuxième", out, flags=re.IGNORECASE)
        out = re.sub(r"\b3(?:e|ème)\b", "troisième", out, flags=re.IGNORECASE)
        return out

    @classmethod
    def _safe_text_for_harness(
        cls,
        candidate: str,
        screen_context: ScreenContext,
        kb_terms: list[str],
        fallback: str = "",
    ) -> str:
        """Garantit que tout texte émis vers I3 respecte le contrat strict des montants."""
        cleaned_raw = re.sub(r"\[btn:\s*([^\]]+)\]", r"\1", candidate or "")
        clean = cls._sanitize_ordinals(cls._enforce_tutoiement(cleaned_raw))
        if not clean:
            return fallback
        if text_is_covered(clean, screen_context, kb_terms):
            return clean
        # Si le LLM a glissé un petit nombre inventé (ex: '2 champs'), on garde les montants d'écran uniquement
        stripped = re.sub(r"\b\d+(?:\s*%)?\b", "", clean)
        stripped = re.sub(r"\s+", " ", stripped).strip(" ,.;:-")
        if stripped and text_is_covered(stripped, screen_context, kb_terms):
            return stripped
        return fallback

    @classmethod
    def _is_usable_node(cls, node: ScreenNode) -> bool:
        if node.password or not node.text:
            return False
        txt_n = cls._norm(node.text)
        return not any(ex in txt_n for ex in JURY_DRAWER_EXCLUDES)

    @classmethod
    def _to_french_text(cls, raw_text: str) -> str:
        """Convertit intégralement tout texte Douala/Ewondo vers son équivalent français pour le LLM."""
        clean = re.sub(r"\s+", " ", raw_text or "").strip()
        if not clean:
            return ""
        m_legacy = re.match(r"^(.*?)\s*\[([^\]]+)\]$", clean)
        if m_legacy and m_legacy.group(2).strip() and m_legacy.group(2).strip() not in {"Coché", "Case à cocher"}:
            return m_legacy.group(2).strip()
        key = cls._norm(clean)
        direct = LOCAL_LANG_TO_FR.get(key)
        if direct:
            return direct
        if ":" in clean:
            head, tail = clean.split(":", 1)
            head_fr = LOCAL_LANG_TO_FR.get(cls._norm(head))
            if head_fr:
                tail_fr = cls._to_french_text(tail) if tail.strip() else ""
                return f"{head_fr} : {tail_fr}".strip(" :")
        return clean

    @staticmethod
    def _has_valid_bounds(node: ScreenNode) -> bool:
        b = node.bounds
        return isinstance(b, list) and len(b) == 4 and b[2] > b[0] and b[3] > b[1]

    @classmethod
    def _group_visual_rows(
        cls, screen_context: ScreenContext
    ) -> tuple[list[tuple[str, list[ScreenNode], str]], dict[str, dict[str, str]]]:
        """Regroupe les nœuds en lignes visuelles 100 % françaises (zone principale vs latérale)."""
        nodes = [n for n in screen_context.nodes[:120] if cls._is_usable_node(n)]
        distinct_tops = {n.bounds[1] for n in nodes if cls._has_valid_bounds(n)}
        has_layout = len(distinct_tops) >= 2

        raw_rows: list[tuple[str, list[ScreenNode]]] = []
        current_zone = "main"
        current_row: list[ScreenNode] = []
        row_yc: float | None = None

        i = 0
        while i < len(nodes):
            node = nodes[i]
            if has_layout and cls._has_valid_bounds(node):
                # Regroupe une ligne de liste empilée à gauche (Libellé + Date dessous) avec son montant aligné à droite
                if (
                    i + 2 < len(nodes)
                    and cls._has_valid_bounds(nodes[i + 1])
                    and cls._has_valid_bounds(nodes[i + 2])
                ):
                    n1, n2, n3 = node, nodes[i + 1], nodes[i + 2]
                    t2_n = cls._norm(n2.text or "")
                    dx_sub = abs(n2.bounds[0] - n1.bounds[0])
                    dy_sub = n2.bounds[1] - n1.bounds[3]
                    yc3 = (n3.bounds[1] + n3.bounds[3]) / 2.0
                    is_date_sub = bool(
                        re.search(
                            r"\b\d{1,2}\s+(?:janv|fev|mar|avr|mai|juin|juil|aout|sept|oct|nov|dec)[a-z.]*\s+\d{4}\b",
                            t2_n,
                        )
                    )
                    if (
                        is_date_sub
                        and dx_sub <= 18
                        and -2 <= dy_sub <= 8
                        and not (n1.clickable or n1.tag in {"button", "a", "h1", "h2", "h3"})
                        and not extract_amounts(n1.text or "")
                        and not (n3.clickable or n3.tag in {"button", "a"})
                        and bool(extract_amounts(n3.text or ""))
                        and n3.bounds[0] > max(n1.bounds[2], n2.bounds[2]) + 40
                        and (n1.bounds[1] - 6) <= yc3 <= (n2.bounds[3] + 6)
                    ):
                        if current_row:
                            raw_rows.append((current_zone, current_row))
                            current_row = []
                        if row_yc is not None and n1.bounds[1] < row_yc - 35:
                            current_zone = "sidebar"
                        raw_rows.append((current_zone, [n1, n2, n3]))
                        row_yc = (n2.bounds[1] + n2.bounds[3]) / 2.0
                        i += 3
                        continue

                yc = (node.bounds[1] + node.bounds[3]) / 2.0
                last_left = current_row[-1].bounds[0] if (current_row and cls._has_valid_bounds(current_row[-1])) else 0
                if not current_row:
                    if row_yc is not None and node.bounds[1] < row_yc - 35:
                        current_zone = "sidebar"
                    current_row = [node]
                    row_yc = yc
                elif row_yc is not None and node.bounds[1] < row_yc - 35:
                    raw_rows.append((current_zone, current_row))
                    current_zone = "sidebar"
                    current_row = [node]
                    row_yc = yc
                elif row_yc is not None and abs(yc - row_yc) <= 16 and node.bounds[0] >= last_left - 20:
                    current_row.append(node)
                else:
                    raw_rows.append((current_zone, current_row))
                    current_row = [node]
                    row_yc = yc
            else:
                if current_row:
                    raw_rows.append((current_zone, current_row))
                current_row = [node]
                row_yc = None
            i += 1

        if current_row:
            raw_rows.append((current_zone, current_row))

        rows: list[tuple[str, list[ScreenNode], str]] = []
        node_meta: dict[str, dict[str, str]] = {}

        for zone, row_nodes in raw_rows:
            if (
                len(row_nodes) == 3
                and re.search(
                    r"\b\d{1,2}\s+(?:janv|fev|mar|avr|mai|juin|juil|aout|sept|oct|nov|dec)[a-z.]*\s+\d{4}\b",
                    cls._norm(row_nodes[1].text or ""),
                )
                and extract_amounts(row_nodes[2].text or "")
            ):
                t1 = cls._to_french_text(row_nodes[0].text or "")
                t2 = cls._to_french_text(row_nodes[1].text or "")
                t3 = cls._to_french_text(row_nodes[2].text or "")
                row_text = f"{t1} ({t2}) | {t3}"
            else:
                parts: list[str] = []
                seen_parts: set[str] = set()
                for rn in row_nodes:
                    fr_text = cls._to_french_text(rn.text or "")
                    fmt = f"Bouton « {fr_text} »" if (rn.clickable or rn.tag in {"button", "a"}) and fr_text else fr_text
                    if fmt and fmt not in seen_parts:
                        seen_parts.add(fmt)
                        parts.append(fmt)
                row_text = " | ".join(parts)
            rows.append((zone, row_nodes, row_text))

            for rn in row_nodes:
                raw_clean = re.sub(r"\s+", " ", rn.text or "").strip()
                m_legacy = re.match(r"^(.*?)\s*\[([^\]]+)\]$", raw_clean)
                raw_no_gloss = (
                    m_legacy.group(1).strip()
                    if (m_legacy and m_legacy.group(2).strip() not in {"Coché", "Case à cocher"})
                    else raw_clean
                )
                fr_text = cls._to_french_text(raw_clean)
                node_meta[rn.node_id] = {
                    "zone": zone,
                    "row_text": row_text,
                    "annotated": fr_text,
                    "raw_no_gloss": raw_no_gloss,
                    "gloss_only": fr_text,
                }

        return rows, node_meta

    @classmethod
    def _analyze_screen(
        cls, screen_context: ScreenContext
    ) -> dict[str, Any]:
        """Extrait la structure sémantique (lignes, paires champ/valeur, alertes, boutons, sous-titres)."""
        rows, node_meta = cls._group_visual_rows(screen_context)
        usable_nodes = [n for n in screen_context.nodes[:120] if cls._is_usable_node(n)]
        nodes_by_id = {n.node_id: n for n in usable_nodes}

        def _is_alert_text(txt_n: str) -> bool:
            return any(
                kw in txt_n
                for kw in (
                    "alerte",
                    "erreur",
                    "insuffisant",
                    "jamais ete utilise",
                    "indisponible",
                    "code secret",
                    "message important",
                    "plafonne",
                    "attention",
                )
            )

        def _is_date_text(txt_n: str) -> bool:
            return bool(re.search(r"\b\d{1,2}\s+(?:janv|fev|mar|avr|mai|juin|juil|aout|sept|oct|nov|dec)[a-z.]*\s+\d{4}\b", txt_n))

        def _is_security_text(txt_n: str, zone: str) -> bool:
            if zone not in {"side", "sidebar"}:
                return False
            return any(
                k in txt_n
                for k in (
                    "protection anti-arnaque",
                    "connexion securisee",
                    "verifie toujours le nom",
                    "verifiez toujours le nom",
                    "beneficiaire avant d'envoyer",
                    "beneficiaire avant de confirmer",
                    "securite",
                )
            )

        def _is_subtitle_node(node: ScreenNode, meta: dict[str, str]) -> bool:
            fr_n = cls._norm(meta.get("gloss_only") or node.text)
            if not fr_n or _is_alert_text(fr_n) or _is_security_text(fr_n, meta.get("zone") or "main"):
                return False
            if node.clickable or node.tag in {"input", "select", "button", "a"}:
                return False
            if extract_amounts(fr_n) or "j'ai verifie" in fr_n or "je confirme" in fr_n:
                return False
            return len(fr_n) >= 34 and (node.tag in {"p", "h2", "h1", "div"} or fr_n.endswith("."))

        # Index de zone et rôle de chaque nœud
        alerts: list[dict[str, str]] = []
        buttons: list[dict[str, str]] = []
        security_nodes: list[dict[str, str]] = []
        subtitles: set[str] = set()
        field_pairs: list[dict[str, Any]] = []
        label_to_value: dict[str, str] = {}
        value_to_label: dict[str, str] = {}
        checkbox_nodes: set[str] = set()

        for n in usable_nodes:
            meta = node_meta.get(n.node_id, {})
            fr_txt = meta.get("gloss_only") or cls._to_french_text(n.text or "")
            fr_n = cls._norm(fr_txt)
            zone = meta.get("zone") or "main"
            is_btn = bool(n.clickable or n.tag in {"button", "a"})

            if _is_alert_text(fr_n):
                is_err = any(k in fr_n for k in ("erreur", "insuffisant", "indisponible", "code secret"))
                alerts.append({"text": fr_txt, "node_id": n.node_id, "zone": zone, "is_error": "1" if is_err else "0"})
                meta["role"] = "alert"
            elif _is_security_text(fr_n, zone):
                meta["role"] = "security"
                security_nodes.append({"text": fr_txt, "node_id": n.node_id})
            elif is_btn and "[case a cocher]" not in fr_n and "[coche]" not in fr_n:
                buttons.append({"text": fr_txt, "node_id": n.node_id, "zone": zone})
                meta["role"] = "button"
            elif _is_subtitle_node(n, meta):
                subtitles.add(n.node_id)
                meta["role"] = "subtitle"
            elif n.tag in {"input", "select"}:
                meta["role"] = "input"
            else:
                meta["role"] = "text"

        # 1. Paires horizontales (ex: 'Frais | Gratuit | 0 FCFA', '[Case à cocher] | J\'ai vérifié...')
        for zone, row_nodes, _ in rows:
            texts = [node_meta.get(rn.node_id, {}).get("gloss_only") or cls._to_french_text(rn.text or "") for rn in row_nodes]
            norms = [cls._norm(t) for t in texts]
            if any(nt in {"[case a cocher]", "[coche]"} for nt in norms) and len(row_nodes) >= 2:
                checked = any(nt == "[coche]" for nt in norms)
                text_nodes = [rn for rn, nt in zip(row_nodes, norms) if nt not in {"[case a cocher]", "[coche]"}]
                if text_nodes:
                    target_rn = text_nodes[0]
                    lbl_txt = node_meta[target_rn.node_id]["gloss_only"]
                    checkbox_nodes.add(target_rn.node_id)
                    node_meta[target_rn.node_id]["role"] = "checkbox"
                    for rn in row_nodes:
                        if rn.node_id != target_rn.node_id:
                            label_to_value[rn.node_id] = target_rn.node_id
                            checkbox_nodes.add(rn.node_id)
                    field_pairs.append({
                        "label": "Case à cocher",
                        "value": f"{lbl_txt} ({'cochée' if checked else 'non cochée'})",
                        "raw_value": lbl_txt,
                        "label_id": target_rn.node_id,
                        "value_id": target_rn.node_id,
                        "zone": zone,
                        "kind": "checkbox",
                    })
                continue

            if len(row_nodes) >= 2:
                first_n = row_nodes[0]
                first_txt = texts[0]
                last_n = row_nodes[-1]
                last_txt = texts[-1]
                is_tx_triple = (
                    len(row_nodes) == 3
                    and _is_date_text(norms[1])
                    and bool(extract_amounts(last_txt))
                )
                has_btn_in_row = any(rn.clickable or rn.tag in {"button", "a"} for rn in row_nodes)
                is_genuine_value = (
                    is_tx_triple
                    or bool(extract_amounts(last_txt))
                    or last_n.tag in {"input", "select"}
                    or (len(row_nodes) >= 3 and texts[1].lower() in {"gratuit", "bonam"})
                    or (
                        len(row_nodes) == 2
                        and not has_btn_in_row
                        and not _is_date_text(norms[0])
                        and len(first_txt) >= 3
                        and not (first_txt.isupper() and len(first_txt) <= 3)
                    )
                )
                if (
                    is_genuine_value
                    and not (first_n.clickable or first_n.tag in {"button", "a"})
                    and not extract_amounts(first_txt)
                    and len(first_txt) <= 36
                    and first_n.node_id not in subtitles
                ):
                    # Cas particulier : <input value="25000"> | FCFA
                    if first_n.tag == "input" and last_txt.upper() in {"FCFA", "XAF", "€", "$"}:
                        pass
                    else:
                        badge = texts[1] if len(row_nodes) >= 3 else ""
                        if is_tx_triple:
                            display_val = f"{last_txt} ({badge})"
                        elif badge and badge.lower() in {"gratuit", "bonam"}:
                            display_val = f"{last_txt} ({badge})"
                        else:
                            display_val = last_txt
                        label_to_value[first_n.node_id] = last_n.node_id
                        value_to_label[last_n.node_id] = first_txt
                        field_pairs.append({
                            "label": first_txt,
                            "value": display_val,
                            "raw_value": last_txt,
                            "label_id": first_n.node_id,
                            "value_id": last_n.node_id,
                            "zone": zone,
                            "kind": "transaction" if is_tx_triple else "row",
                        })

        # 2. Paires verticales (ex: <label>Nom du bénéficiaire</label> au-dessus de <input>Jean-Paul Mbarga</input>)
        for idx, lbl_n in enumerate(usable_nodes):
            lbl_meta = node_meta.get(lbl_n.node_id, {})
            if lbl_n.tag in {"input", "select", "textarea", "h1", "h2", "h3"} or lbl_n.node_id in value_to_label:
                continue
            if lbl_n.node_id in label_to_value or lbl_n.node_id in subtitles or lbl_n.node_id in checkbox_nodes:
                continue
            if lbl_meta.get("role") in {"button", "alert", "security"}:
                continue
            lbl_txt = lbl_meta.get("gloss_only") or ""
            if not lbl_txt or len(lbl_txt) > 42 or extract_amounts(lbl_txt):
                continue
            if extract_amounts(lbl_meta.get("row_text") or ""):
                continue
            if not cls._has_valid_bounds(lbl_n):
                continue
            lbl_zone = lbl_meta.get("zone") or "main"

            for cand_n in usable_nodes[idx + 1 : idx + 5]:
                cand_meta = node_meta.get(cand_n.node_id, {})
                if (cand_meta.get("zone") or "main") != lbl_zone:
                    continue
                if cand_meta.get("role") in {"button", "alert"} or cand_n.tag in {"h1", "h2", "h3"}:
                    continue
                if cand_n.node_id in label_to_value:
                    continue
                if not cls._has_valid_bounds(cand_n):
                    continue
                dy = cand_n.bounds[1] - lbl_n.bounds[3]
                dx = abs(cand_n.bounds[0] - lbl_n.bounds[0])
                if -4 <= dy <= 44 and dx <= 65:
                    cand_txt = cand_meta.get("gloss_only") or ""
                    if not cand_txt or cand_n.node_id in subtitles or _is_date_text(cls._norm(cand_txt)):
                        continue
                    is_micro_lbl = (lbl_n.bounds[3] - lbl_n.bounds[1]) <= 18 or lbl_txt.isupper()
                    is_val_candidate = (
                        cand_n.tag in {"input", "select"}
                        or bool(extract_amounts(cand_txt))
                        or (len(cand_txt) <= 44 and lbl_n.tag == "label")
                        or (len(cand_txt) <= 36 and len(lbl_txt) <= 28 and is_micro_lbl and cand_n.bounds[3] - cand_n.bounds[1] >= 20)
                    )
                    if is_val_candidate and cand_n.node_id not in value_to_label:
                        display_val = cand_txt
                        row_txt_norm = cand_meta.get("row_text") or ""
                        if cand_n.tag == "input" and "FCFA" in row_txt_norm and "FCFA" not in cand_txt:
                            display_val = f"{cand_txt} FCFA"
                        label_to_value[lbl_n.node_id] = cand_n.node_id
                        value_to_label[cand_n.node_id] = lbl_txt
                        field_pairs.append({
                            "label": lbl_txt,
                            "value": display_val,
                            "raw_value": cand_txt,
                            "label_id": lbl_n.node_id,
                            "value_id": cand_n.node_id,
                            "zone": lbl_zone,
                            "kind": "input" if cand_n.tag in {"input", "select"} else "metric",
                        })
                        break

        return {
            "rows": rows,
            "node_meta": node_meta,
            "usable_nodes": nodes_by_id,
            "field_pairs": field_pairs,
            "label_to_value": label_to_value,
            "value_to_label": value_to_label,
            "alerts": alerts,
            "buttons": buttons,
            "security_nodes": security_nodes,
            "subtitles": subtitles,
            "checkbox_nodes": checkbox_nodes,
        }

    def _find_amount_node(self, screen_context: ScreenContext) -> tuple[str | None, str | None]:
        """Localise le montant financier le plus spécifique et son node_id dans l'arbre d'accessibilité."""
        for node in reversed(screen_context.nodes):
            if not self._is_usable_node(node):
                continue
            amounts = extract_amounts(node.text)
            if amounts and len(node.text.strip()) <= 20:
                return node.text.strip(), node.node_id

        for node in screen_context.nodes:
            if not self._is_usable_node(node):
                continue
            amounts = extract_amounts(node.text)
            if amounts:
                first_amt = next(iter(amounts))
                return first_amt.upper(), node.node_id

        return None, None

    def _build_llm_prompt(self, transcript: Transcript, screen_context: ScreenContext) -> str:
        """Construit un prompt compact avec préfixe d'écran stable (optimisé pour le cache KV d'Ollama et ~300ms de latence)."""
        semantics = self._analyze_screen(screen_context)
        rows = semantics["rows"]
        prompt_lines: list[str] = []
        last_zone: str | None = None
        for zone, _, row_text in rows[:35]:
            if not row_text:
                continue
            if zone != last_zone:
                prompt_lines.append("Zone principale:" if zone == "main" else "Panneau latéral:")
                last_zone = zone
            prompt_lines.append(f"- {row_text}")

        page_title = screen_context.page.title if screen_context.page and screen_context.page.title else "Safinum"
        hint = screen_context.screen_hint or "home"

        return (
            f"Tu es NKAP, copilote bancaire vocal et visuel style HeyClicky. Application: {page_title} (étape: {hint}).\n"
            "Contenu structuré de l'écran:\n"
            + ("\n".join(prompt_lines) if prompt_lines else "(vide)")
            + "\n\nConsigne: indique l'élément exact de l'écran (valeur ou libellé de bouton) qui répond à la question, ou 0 si absent ou hors-sujet.\n"
            "Réponds en 1 à 4 mots maximum (valeur exacte, pas d'explication).\n"
            f"Question: {transcript.text}\n"
            "Élément:"
        )

    @classmethod
    def _resolve_target_node(
        cls,
        target_query: str,
        context_query: str,
        usable_nodes: dict[str, ScreenNode],
        node_meta: dict[str, dict[str, str]],
        semantics: dict[str, Any] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> str | None:
        """Associe le texte cité et la réponse vocale au meilleur nœud DOM (jamais au sous-titre décoratif)."""
        q_clean = re.sub(r"\s*\(=\s*[^)]+\)", "", target_query or "").strip()
        q_t = cls._norm(q_clean)
        q_ctx = cls._norm(context_query)
        q_amounts = extract_amounts(target_query or "")
        ctx_amounts = extract_amounts(context_query or "")

        subtitles: set[str] = semantics.get("subtitles", set()) if semantics else set()
        label_to_value: dict[str, str] = semantics.get("label_to_value", {}) if semantics else {}

        stopwords = {
            "avec", "sans", "dans", "pour", "sur", "sous", "entre", "vers", "chez",
            "ton", "tes", "mon", "mes", "son", "ses", "votre", "notre", "leur",
            "est", "sont", "cest", "cette", "cet", "ces", "une", "des", "les", "aux",
            "toujours", "jamais", "avant", "apres", "peux", "dois", "faut", "voici",
            "ecran", "actuel", "regarde", "affiche", "affiches", "application", "quel", "quelle",
            "suis", "disponible", "verifier", "verifie", "valider", "continuer", "informations",
        }
        t_tokens = {tok for tok in re.findall(r"[a-z0-9]{3,}", q_t) if tok not in stopwords}
        ctx_tokens = {tok for tok in re.findall(r"[a-z0-9]{3,}", q_ctx) if tok not in stopwords}

        best_id: str | None = None
        best_score = 0

        for nid, node in usable_nodes.items():
            if exclude_ids and nid in exclude_ids:
                continue
            meta = node_meta.get(nid, {})
            n_raw = cls._norm(meta.get("raw_no_gloss") or node.text)
            n_gloss = cls._norm(meta.get("gloss_only") or "")
            n_ann = cls._norm(meta.get("annotated") or node.text)
            row_norm = cls._norm(meta.get("row_text") or "")
            zone = meta.get("zone") or "main"
            if not n_raw:
                continue

            node_amounts = extract_amounts(node.text or "")
            target_score = 0
            evidence_score = 0

            if q_t:
                if n_raw == q_t or (n_gloss and n_gloss == q_t):
                    target_score += 28
                elif q_amounts and (node_amounts & q_amounts):
                    target_score += 26
                elif (len(q_t) >= 3 and q_t in n_raw) or (len(n_raw) >= 4 and n_raw in q_t):
                    target_score += 14
                elif (len(q_t) >= 3 and n_gloss and q_t in n_gloss) or (n_gloss and len(n_gloss) >= 4 and n_gloss in q_t):
                    target_score += 14
                if t_tokens:
                    target_score += sum(4 for tok in t_tokens if tok in n_ann)

            # Preuve directe dans la réponse vocale / question
            if ctx_amounts and (node_amounts & ctx_amounts):
                evidence_score += 36
                if len(n_raw) <= 24:
                    evidence_score += 6
            elif len(n_raw) >= 4 and n_raw in q_ctx:
                evidence_score += 28
            elif ctx_tokens:
                evidence_score += sum(4 for tok in ctx_tokens if tok in n_ann)

            if target_score == 0 and evidence_score == 0 and not (
                meta.get("role") == "security" and any(k in (q_t + " " + q_ctx) for k in ("arnaqu", "securite", "fraude", "proteg", "prudence"))
            ):
                continue

            score = target_score + evidence_score
            if meta.get("role") == "security" and any(k in (q_t + " " + q_ctx) for k in ("arnaqu", "securite", "fraude", "proteg", "prudence")):
                score += 22
            if ctx_tokens and row_norm:
                score += sum(2 for tok in ctx_tokens if tok in row_norm)
            if zone == "main":
                score += 6
            if len(n_raw) <= 32:
                score += 2
            if node.tag in {"input", "select"} or (semantics and nid in semantics.get("value_to_label", {})):
                score += 14
            if (node.text or "").strip().isupper() and len(n_raw) <= 24 and not node_amounts and not node.clickable and node.tag not in {"input", "select"}:
                score -= 14  # Évite les titres de section décoratifs ("BÉNÉFICIAIRE", "VOTRE COMPTE")
            if nid in subtitles:
                score -= 22  # Empêche les phrases d'en-tête décoratives de voler le focus aux champs/valeurs

            if score > best_score:
                best_score = score
                best_id = nid

        if not best_id or best_score < 6:
            return None

        # Si on a pointé le libellé d'un champ (ex: "Nom du bénéficiaire"), glisse vers sa valeur/champ associé
        snapped = label_to_value.get(best_id)
        if snapped and snapped in usable_nodes and (not exclude_ids or snapped not in exclude_ids):
            return snapped
        return best_id

    @classmethod
    def _choose_heyclicky_style(
        cls,
        node: ScreenNode,
        semantics: dict[str, Any],
        requested_style: str | None,
        question_norm: str,
        is_explicit_style: bool = False,
    ) -> tuple[str, str | None]:
        """Choisit le geste HeyClicky le plus expressif (box, circle, frame + label, underline)."""
        if is_explicit_style and requested_style in ALLOWED_HIGHLIGHT_STYLES:
            return requested_style, "Appuie ici" if requested_style == "frame" else None

        meta = semantics["node_meta"].get(node.node_id, {})
        role = meta.get("role", "text")
        txt_n = cls._norm(meta.get("gloss_only") or node.text)

        if role == "button" or node.clickable or node.tag in {"button", "a"}:
            if node.node_id in semantics["checkbox_nodes"] or "[case a cocher]" in txt_n or "[coche]" in txt_n:
                return ("frame", "Coche ici") if any(k in question_norm for k in ("coch", "valider", "continuer", "comment", "faire")) else ("box", None)
            return "frame", "Appuie ici"

        if node.node_id in semantics["checkbox_nodes"]:
            return ("frame", "Coche ici") if any(k in question_norm for k in ("coch", "valider", "continuer", "comment")) else ("box", None)

        if role == "alert":
            return "box", None

        if node.tag in {"input", "select"} or node.node_id in semantics["value_to_label"]:
            return "box", None

        # Solde principal ou statut de succès isolé -> cercle manuscrit si explicitement seul
        if extract_amounts(txt_n) and len(txt_n) <= 22 and any(k in question_norm for k in ("solde", "disponible", "combien il me reste")):
            return "circle", None
        if any(k in txt_n for k in ("confirme", "effectue", "succes")) and len(txt_n) <= 28:
            return "circle", None

        # Évite de remplacer systématiquement tout champ/valeur par un simple underline
        if requested_style in {"box", "circle", "frame"}:
            return requested_style, "Appuie ici" if requested_style == "frame" else None
        return "box", None

    def _infer_extra_semantic_targets(
        self,
        question_text: str,
        semantics: dict[str, Any],
        already_ids: list[str],
    ) -> list[str]:
        """Si la question nomme explicitement plusieurs champs/actions présents à l'écran, les capture sans rien inventer."""
        q_n = self._norm(question_text)
        extra_ids: list[str] = []
        stop = {"pour", "dans", "avec", "quel", "quelle", "quoi", "comment", "faire", "avant", "apres", "mon", "ton", "est", "sont"}
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", q_n) if t not in stop}

        # Cherche dans les paires champ/valeur détectées
        for p in semantics["field_pairs"]:
            if p["zone"] != "main":
                continue
            lbl_n = self._norm(p["label"])
            val_n = self._norm(p["raw_value"])
            lbl_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", lbl_n) if t not in stop}
            matched = bool(q_tokens & lbl_tokens) or (p["kind"] == "checkbox" and ("coch" in q_n or "case" in q_n))
            if matched:
                vid = p["value_id"]
                if vid not in already_ids and vid not in extra_ids:
                    extra_ids.append(vid)

        # Si la question demande comment continuer / valider / envoyer (hors "où vérifier..."), capture le bouton principal
        asks_action = (
            any(k in q_n for k in ("continuer", "suivant", "valider", "confirmer", "appuyer", "comment"))
            and not ("ou " in q_n and "verifi" in q_n)
            and "arnaqu" not in q_n
            and "alerte" not in q_n
        )
        if asks_action:
            for b in semantics["buttons"]:
                if b["zone"] != "main":
                    continue
                bn = self._norm(b["text"])
                if any(tok in bn for tok in q_tokens) or any(cta in bn for cta in ("continuer", "effectuer un transfert", "confirmer")):
                    if b["node_id"] not in already_ids and b["node_id"] not in extra_ids:
                        extra_ids.append(b["node_id"])
                        break

        return extra_ids

    def _compile_legacy_check_balance(
        self, llm_payload: dict[str, Any], transcript: Transcript, screen_context: ScreenContext
    ) -> list[ActionMessage]:
        """Compatibilité stricte avec les tests unitaires M2 existants sur `check_balance`."""
        lang = transcript.lang or "ewo"
        sb = _StreamBuilder(transcript, transcript.ts or 0)
        screen_amount, screen_node_id = self._find_amount_node(screen_context)
        llm_amount = llm_payload.get("amount")

        amount = screen_amount
        if llm_amount and screen_amount and re.sub(r"\D", "", str(llm_amount)) == re.sub(r"\D", "", screen_amount):
            amount = str(llm_amount)

        target_node_id = screen_node_id or (screen_context.nodes[0].node_id if screen_context.nodes else "n_01")
        phrase = self.kb.get_phrase("balance_answer", lang=lang)
        if phrase and amount:
            phrase = phrase.replace("{amount}", amount)
        elif amount:
            phrase = f"Solde wɔ́g á {amount}."

        if phrase:
            sb.speak("balance_answer", phrase, lang, 0)
        if amount and target_node_id:
            sb.draw("circle", "c_1", target_node_id, color="ink", duration_ms=700, run_after_ms=200)
            sb.write("w_1", amount, target_node_id, dy=-66, size=27, per_letter_ms=55, run_after_ms=900)
        return sb.actions

    @classmethod
    def _is_out_of_scope_question(cls, question_text: str, screen_context: ScreenContext) -> bool:
        """Détecte les questions hors-sujet, malveillantes ou impossibles à résoudre avec l'écran actuel."""
        q_n = cls._norm(question_text)
        if not q_n:
            return False

        screen_parts: list[str] = []
        if screen_context.page and screen_context.page.title:
            screen_parts.append(cls._to_french_text(screen_context.page.title))
        for n in screen_context.nodes[:120]:
            if n.password:
                continue
            if n.text:
                screen_parts.append(cls._to_french_text(n.text))
            if n.content_desc:
                screen_parts.append(cls._to_french_text(n.content_desc))
        screen_corpus_n = cls._norm(" ".join(screen_parts))

        # 1. Sujets explicitement hors contexte ou frauduleux (sauf s'ils figurent réellement à l'écran)
        off_topic_keywords = (
            "actionnaire", "actions", "bourse", "investir", "investissement", "dividende",
            "trading", "forex", "crypto", "bitcoin", "ethereum", "doubler", "tripler",
            "multiplier", "argent facile", "gagner vite", "entreprise safinum", "pdg",
            "fondateur", "recrutement", "emploi", "stage", "pirater", "piratage", "hacker",
            "hack", "cracker", "craquer", "contourner", "voler", "frauder", "usurper",
            "voiture", "maison", "appartement", "terrain", "meteo", "recette", "cuisine",
            "football", "billet d'avion", "hotel", "restaurant", "medicament", "hopital",
            "ecole", "universite", "acheter", "credit", "pret", "emprunt", "hypotheque",
            "carte bancaire", "carte visa", "mastercard", "cheque", "taux d'interet",
            "cloturer", "fermer mon compte", "ouvrir un compte", "mot de passe", "code pin",
            "changer mon code", "support client", "service client", "contacter le support",
        )
        for kw in off_topic_keywords:
            if kw in q_n and kw not in screen_corpus_n:
                return True

        # 2. Vérification de recouvrement minimal avec l'écran ou le vocabulaire bancaire de l'app
        stopwords = {
            "alors", "apres", "avant", "avec", "avoir", "beaucoup", "besoin", "bien", "bonjour",
            "bonsoir", "cela", "celle", "celles", "celui", "cest", "cette", "ceux", "chez",
            "chose", "combien", "comme", "comment", "dans", "depuis", "dois", "doit", "donc",
            "ecran", "elle", "encore", "entre", "etre", "explique", "expliquer", "faire",
            "fais", "faut", "info", "infos", "information", "informations", "juste", "leur",
            "leurs", "lire", "mais", "merci", "moins", "notre", "nous", "page", "parle",
            "peut", "peux", "plus", "pour", "pourquoi", "puis", "quand", "quel", "quelle",
            "quelles", "quels", "quelqu", "quelque", "question", "quoi", "regarde", "rien",
            "salut", "sans", "savoir", "sera", "sont", "sous", "suis", "tout", "tous",
            "toute", "toutes", "tres", "truc", "veux", "voici", "voir", "votre", "vous",
            "aide", "aider",
        }
        q_tokens = [t for t in re.findall(r"[a-z0-9]{4,}", q_n) if t not in stopwords]
        if not q_tokens:
            return False

        app_vocab = {
            "application", "safinum", "solde", "argent", "compte", "frais", "transfert",
            "transfe", "envoi", "envoyer", "envoie", "beneficiaire", "destinataire",
            "numero", "telephone", "transaction", "transactions", "operation", "operations",
            "historique", "paiement", "salaire", "recap", "recapitulatif", "confirmer",
            "confirmation", "recu", "reference", "alerte", "avertissement", "erreur",
            "securite", "arnaque", "arnaquer", "fraude", "mefier", "cocher", "case",
            "continuer", "etape", "etapes", "bouton", "montant", "montants", "reste",
            "restera", "debite", "debiter", "payer", "marchand", "facture", "electricite",
            "disponible", "fcfa", "message", "nouveau", "courant", "nom",
        }
        screen_words = set(re.findall(r"[a-z0-9]{3,}", screen_corpus_n))
        for tok in q_tokens:
            if tok in app_vocab or tok in screen_words or tok in screen_corpus_n:
                return False
            # Tolère les formes fléchies (ex: "arnaquer" ~ "arnaque", "transactions" ~ "transaction")
            stem = tok[:5] if len(tok) >= 5 else tok
            if any(w.startswith(stem) for w in (app_vocab | screen_words)):
                return False
        return True

    def _build_out_of_scope_actions(
        self, transcript: Transcript, screen_context: ScreenContext
    ) -> list[ActionMessage]:
        """Réponse sûre et concise lorsque la demande sort du contexte de l'écran."""
        lang = transcript.lang or "fr"
        sb = _StreamBuilder(transcript, transcript.ts or 0)
        refusal_spoken = (
            "Je suis incapable de répondre à cette demande : je n'ai pas ces informations dans cet écran. "
            "Veuillez contacter le support."
        )
        sb.speak("out_of_scope", refusal_spoken, lang, 0)
        sb.notebook(
            "nb-guide",
            "Hors contexte",
            [
                NotebookLine(id="nb-l1", text="• Information absente de cet écran", color="yellow"),
                NotebookLine(divider=True),
                NotebookLine(
                    id="nb-l-act",
                    text="→ Veuillez contacter le support",
                    color="yellow",
                    bold=True,
                    underline=True,
                ),
            ],
            anchor_id=None,
            run_after_ms=0,
        )
        sb.clear(6200)
        return sb.actions

    def _compile_llm_plan(
        self, llm_payload: dict[str, Any], transcript: Transcript, screen_context: ScreenContext
    ) -> list[ActionMessage]:
        """Compile la décision du LLM en chorégraphie HeyClicky fidèle (carnet structuré, gestes typés, voix 2 temps, <= 3 marques)."""
        raw_spoken = str(llm_payload.get("spoken") or "").strip()
        raw_spoken_n = self._norm(raw_spoken)
        if bool(llm_payload.get("out_of_scope")) or any(
            marker in raw_spoken_n
            for marker in (
                "incapable de repondre",
                "hors contexte",
                "hors du cadre",
                "pas assez d'informations",
                "contacter le support",
            )
        ):
            return self._build_out_of_scope_actions(transcript, screen_context)

        lang = transcript.lang or "fr"
        sb = _StreamBuilder(transcript, transcript.ts or 0)
        semantics = self._analyze_screen(screen_context)
        usable_nodes = semantics["usable_nodes"]
        node_meta = semantics["node_meta"]
        kb_terms = self.kb.terms
        q_norm = self._norm(transcript.text)

        spoken = self._safe_text_for_harness(
            raw_spoken,
            screen_context,
            kb_terms,
            fallback="Voici ce qui est affiché sur ton écran actuel.",
        )
        context_query = f"{spoken} {transcript.text}".strip()

        requested_style_raw = str(llm_payload.get("style") or "").lower().strip()
        default_style = requested_style_raw if requested_style_raw in ALLOWED_HIGHLIGHT_STYLES else "box"
        default_color = str(llm_payload.get("color") or "ink").lower()
        if default_color not in ALLOWED_COLORS:
            default_color = "ink"
        default_arrow = llm_payload.get("arrow")

        # 1. Résolution des cibles (IDs explicites OU multi-cibles textuelles résolues géométriquement)
        raw_highlights = llm_payload.get("highlights")
        valid_highlights: list[dict[str, Any]] = []
        used_explicit_node_ids = False

        if isinstance(raw_highlights, list):
            for h in raw_highlights:
                if isinstance(h, str):
                    nid = h.strip("[] ").strip()
                    if nid in usable_nodes:
                        used_explicit_node_ids = True
                        valid_highlights.append(
                            {"node_id": nid, "style": default_style, "color": default_color}
                        )
                elif isinstance(h, dict):
                    nid = str(h.get("node_id") or "").strip("[] ").strip()
                    if nid in usable_nodes:
                        used_explicit_node_ids = True
                        item_copy = dict(h)
                        item_copy["_explicit_style"] = "style" in h
                        valid_highlights.append(item_copy)

        raw_targets = llm_payload.get("targets")
        had_invalid_id = False
        if not valid_highlights and isinstance(raw_targets, list):
            for t_item in raw_targets:
                raw_val = (
                    t_item.strip("[] ").strip()
                    if isinstance(t_item, str)
                    else str(t_item.get("node_id") or t_item.get("text") or "").strip("[] ").strip()
                    if isinstance(t_item, dict)
                    else ""
                )
                if not raw_val:
                    continue
                if raw_val in usable_nodes:
                    used_explicit_node_ids = True
                    resolved_id = raw_val
                elif re.match(r"^n_[a-z0-9_-]+$", raw_val, re.IGNORECASE):
                    had_invalid_id = True
                    resolved_id = None
                else:
                    resolved_id = self._resolve_target_node(
                        raw_val,
                        context_query,
                        usable_nodes,
                        node_meta,
                        semantics=semantics,
                        exclude_ids={h["node_id"] for h in valid_highlights},
                    )
                if resolved_id and all(h["node_id"] != resolved_id for h in valid_highlights):
                    valid_highlights.append(
                        {
                            "node_id": resolved_id,
                            "style": default_style,
                            "color": default_color,
                            "arrow_from_notebook": default_arrow,
                            "_explicit_node_id": raw_val in usable_nodes,
                        }
                    )

        # Résolution via `target_text` (ancien format compact)
        target_text_val = str(llm_payload.get("target_text") or "").strip()
        if not valid_highlights and not had_invalid_id and target_text_val:
            resolved_id = self._resolve_target_node(
                target_text_val, context_query, usable_nodes, node_meta, semantics=semantics
            )
            if resolved_id:
                valid_highlights.append(
                    {
                        "node_id": resolved_id,
                        "style": default_style,
                        "color": default_color,
                        "arrow_from_notebook": True if default_arrow is None else bool(default_arrow),
                    }
                )

        if not valid_highlights and llm_payload.get("target_node_id"):
            nid = str(llm_payload.get("target_node_id")).strip("[] ").strip()
            if nid in usable_nodes:
                used_explicit_node_ids = True
                valid_highlights.append(
                    {"node_id": nid, "style": default_style, "color": default_color, "arrow_from_notebook": True}
                )

        if not valid_highlights and not had_invalid_id and default_arrow is not False and usable_nodes:
            grounded_id = self._resolve_target_node(
                "", context_query, usable_nodes, node_meta, semantics=semantics
            )
            if grounded_id:
                valid_highlights.append(
                    {
                        "node_id": grounded_id,
                        "style": default_style,
                        "color": default_color,
                        "arrow_from_notebook": True,
                    }
                )

        # Complète automatiquement si la question demande explicitement deux champs/actions distincts (ex: nom ET numéro)
        if not used_explicit_node_ids and not had_invalid_id:
            if any(k in q_norm for k in ("arnaqu", "fraude", "scam", "mefier")) and semantics.get("security_nodes"):
                # Aligne uniquement vers l'encadré Sécurité (conseil principal) sans parasite secondaire
                best_sec = max(semantics["security_nodes"], key=lambda s: len(s["text"]))
                valid_highlights = [{"node_id": best_sec["node_id"], "style": "box", "color": "yellow"}]
            else:
                extra_ids = self._infer_extra_semantic_targets(
                    transcript.text, semantics, [h["node_id"] for h in valid_highlights]
                )
                # Sur "où vérifier le nom et le numéro ?", on privilégie les vrais champs/valeurs du formulaire
                if "ou " in q_norm and "verifi" in q_norm and extra_ids:
                    btn_ids = {b["node_id"] for b in semantics["buttons"]}
                    kept = [
                        h for h in valid_highlights
                        if h["node_id"] not in btn_ids
                        and (h["node_id"] in semantics["value_to_label"] or usable_nodes[h["node_id"]].tag in {"input", "select"})
                    ]
                    for eid in extra_ids:
                        if all(h["node_id"] != eid for h in kept):
                            kept.append({"node_id": eid, "style": "box", "color": default_color})
                    valid_highlights = kept[:2]
                elif len(valid_highlights) < 2:
                    for eid in extra_ids:
                        if len(valid_highlights) >= 2:
                            break
                        if (
                            len(valid_highlights) == 1
                            and valid_highlights[0]["node_id"] in semantics["subtitles"]
                        ):
                            valid_highlights = [{"node_id": eid, "style": "box", "color": default_color}]
                        else:
                            valid_highlights.append({"node_id": eid, "style": "box", "color": default_color})

        # Ajuste intelligemment le geste HeyClicky sur chaque cible (jamais de simple underline sur un champ/bouton/alerte)
        for h in valid_highlights:
            nid = h["node_id"]
            node = usable_nodes.get(nid)
            if not node:
                continue
            is_explicit = bool(h.get("_explicit_style"))
            chosen_style, cta_label = self._choose_heyclicky_style(
                node,
                semantics,
                h.get("style"),
                q_norm,
                is_explicit_style=is_explicit,
            )
            if not (used_explicit_node_ids and requested_style_raw == "box" and len(valid_highlights) > 1):
                h["style"] = chosen_style
            if cta_label and not h.get("label"):
                h["label"] = cta_label
            # Couleur alerte/erreur cohérente
            if node_meta.get(nid, {}).get("role") == "alert" and h.get("color", "ink") == "ink":
                alert_entry = next((a for a in semantics["alerts"] if a["node_id"] == nid), None)
                h["color"] = "red" if (alert_entry and alert_entry["is_error"] == "1") else "yellow"

        # Trie de haut en bas lorsque deux champs/valeurs sont montrés ensemble (ex: Nom puis Numéro)
        is_cta_pair = (
            not used_explicit_node_ids
            and llm_payload.get("notebook_lines") is None
            and len(valid_highlights) == 2
            and valid_highlights[1].get("style") == "frame"
            and any(k in q_norm for k in ("comment", "etape", "suivant", "coch", "confirmer", "envoyer", "fais quoi"))
        )
        if not used_explicit_node_ids and len(valid_highlights) >= 2 and not is_cta_pair:
            valid_highlights.sort(
                key=lambda h: (
                    usable_nodes[h["node_id"]].bounds[1] if h["node_id"] in usable_nodes else 9999,
                    usable_nodes[h["node_id"]].bounds[0] if h["node_id"] in usable_nodes else 9999,
                )
            )

        # Ancrage sur les données concrètes des cibles résolues
        first_role = node_meta.get(valid_highlights[0]["node_id"], {}).get("role", "text") if valid_highlights else "text"
        grounded_facts: list[tuple[str, str]] = []
        highlight_ids = {h["node_id"] for h in valid_highlights}
        for p in semantics["field_pairs"]:
            if p["value_id"] in highlight_ids or p["label_id"] in highlight_ids:
                grounded_facts.append((p["label"], p["value"]))

        # Si `spoken` est trop générique alors qu'on a des faits précis, enrichit ou ancre le texte vocal
        spoken_n = self._norm(spoken)
        if grounded_facts and first_role not in {"alert", "security"} and not any(self._norm(val.split(" (")[0]) in spoken_n for _, val in grounded_facts):
            fact_summary = " et ".join(f"{lbl} : {val}" for lbl, val in grounded_facts[:2])
            if not raw_spoken:
                lbl0, val0 = grounded_facts[0]
                if "solde" in q_norm or "solde" in lbl0.lower():
                    candidate_spoken = f"Ton solde disponible est de {val0}."
                elif "frais" in q_norm or "frais" in lbl0.lower():
                    candidate_spoken = f"Tes frais de transfert sont de {val0}."
                elif "total" in q_norm or "total" in lbl0.lower():
                    candidate_spoken = f"Le montant total débité sera de {val0}."
                elif any(k in q_norm for k in ("beneficiaire", "nom", "destinataire")):
                    candidate_spoken = f"Le bénéficiaire est {val0}."
                else:
                    candidate_spoken = f"{fact_summary}."
            elif len(spoken) < 40 or "regard" in spoken_n or "verifi" in spoken_n or "cette information" in spoken_n:
                candidate_spoken = f"{fact_summary}. {spoken}"
            else:
                candidate_spoken = spoken
            spoken = self._safe_text_for_harness(candidate_spoken, screen_context, kb_terms, fallback=spoken)

        sb.speak("llm_answer", spoken, lang, 0)

        # 2. Carnet HeyClicky structuré (`rows` / `notebook_lines` / `points`)
        raw_nb_title = str(llm_payload.get("notebook_title") or llm_payload.get("title") or "").strip()
        raw_lines = (
            llm_payload.get("rows")
            if llm_payload.get("rows") is not None
            else llm_payload.get("notebook_lines")
            if llm_payload.get("notebook_lines") is not None
            else llm_payload.get("points")
        )
        if not raw_nb_title and grounded_facts and first_role not in {"button"}:
            raw_nb_title = grounded_facts[0][0]
            if raw_lines is None:
                raw_lines = [f"{lbl} : {val}" for lbl, val in grounded_facts[:2]]

        nb_title = self._safe_text_for_harness(raw_nb_title, screen_context, kb_terms, fallback="")
        compiled_lines: list[NotebookLine] = []
        arrow_source_id: str | None = None
        accent_color = default_color if default_color in {"yellow", "red", "green"} else "yellow"

        if nb_title and isinstance(raw_lines, list):
            cleaned_items = [item for item in raw_lines[:4] if item]
            # Détecte si les lignes textuelles fournies par un petit modèle sont purement génériques sans valeur de l'écran
            is_generic_prose = (
                bool(grounded_facts)
                and first_role not in {"alert", "security"}
                and llm_payload.get("notebook_lines") is None
                and all(isinstance(it, str) for it in cleaned_items)
                and not any(
                    re.search(r"\d", str(it))
                    or any(self._norm(val.split(" (")[0]) in self._norm(str(it)) for _, val in grounded_facts)
                    for it in cleaned_items
                )
            )
            if is_generic_prose:
                for idx, (lbl, val) in enumerate(grounded_facts[:2]):
                    lid = f"nb-l{idx + 1}"
                    s_lbl = self._safe_text_for_harness(lbl, screen_context, kb_terms, fallback=lbl)[:28]
                    s_val = self._safe_text_for_harness(val, screen_context, kb_terms, fallback=val)[:28]
                    compiled_lines.append(
                        NotebookLine(
                            id=lid,
                            label=s_lbl,
                            value=s_val,
                            color="green" if "0 fcfa" in s_val.lower() or "gratuit" in s_val.lower() else "yellow" if idx == len(grounded_facts[:2]) - 1 else None,
                            bold=True if idx == len(grounded_facts[:2]) - 1 else None,
                        )
                    )
                    arrow_source_id = f"{lid}-val"
                compiled_lines.append(NotebookLine(divider=True))
                cta_line = "→ Vérifie chaque chiffre ici" if any(k in q_norm for k in ("nom", "numero", "telephone", "alerte")) else "→ Regarde cet élément"
                compiled_lines.append(
                    NotebookLine(
                        id=f"nb-l{len(grounded_facts[:2]) + 1}",
                        text=cta_line,
                        color=accent_color,
                        bold=True,
                        underline=True,
                    )
                )
                arrow_source_id = f"nb-l{len(grounded_facts[:2]) + 1}"
            else:
                for idx, item in enumerate(cleaned_items):
                    lid = f"nb-l{idx + 1}"
                    if isinstance(item, str):
                        raw_str = self._safe_text_for_harness(item, screen_context, kb_terms, fallback="")[:72]
                        if not raw_str:
                            continue
                        is_last = idx == len(cleaned_items) - 1 and len(cleaned_items) >= 2
                        # Découpe automatique 'Libellé : Valeur' (sauf bullet/flèche) en colonnes HeyClicky !
                        if (
                            ":" in raw_str
                            and not raw_str.lstrip().startswith(("•", "→", "-"))
                            and len(raw_str.split(":", 1)[0].strip()) <= 26
                            and len(raw_str.split(":", 1)[1].strip()) <= 28
                        ):
                            lbl_p, val_p = raw_str.split(":", 1)
                            if self._norm(lbl_p) == self._norm(val_p):
                                continue
                            compiled_lines.append(
                                NotebookLine(
                                    id=lid,
                                    label=lbl_p.strip(),
                                    value=val_p.strip(),
                                    color=accent_color if is_last else None,
                                    bold=True if is_last else None,
                                )
                            )
                            arrow_source_id = f"{lid}-val"
                        else:
                            if is_last and len(compiled_lines) >= 1 and llm_payload.get("notebook_lines") is None:
                                compiled_lines.append(NotebookLine(divider=True))
                            compiled_lines.append(
                                NotebookLine(
                                    id=lid,
                                    text=raw_str,
                                    color=accent_color if is_last else None,
                                    underline=True if is_last else None,
                                )
                            )
                            arrow_source_id = lid
                    elif isinstance(item, dict):
                        color = item.get("color") if item.get("color") in ALLOWED_COLORS else None
                        bold = bool(item.get("bold")) if item.get("bold") is not None else None
                        underline = bool(item.get("underline")) if item.get("underline") is not None else None
                        lbl = self._safe_text_for_harness(str(item.get("label") or ""), screen_context, kb_terms, fallback="")
                        val = self._safe_text_for_harness(str(item.get("value") or ""), screen_context, kb_terms, fallback="")
                        txt = self._safe_text_for_harness(str(item.get("text") or ""), screen_context, kb_terms, fallback="")
                        if len(lbl) > 32:
                            lbl = lbl[:32].rsplit(" ", 1)[0]
                        if len(val) > 36:
                            val = val[:36].rsplit(" ", 1)[0]
                        if lbl and val:
                            if self._norm(lbl) == self._norm(val):
                                continue
                            compiled_lines.append(
                                NotebookLine(
                                    id=lid,
                                    label=lbl,
                                    value=val,
                                    color=color,
                                    bold=bold,
                                    underline=underline,
                                )
                            )
                            arrow_source_id = f"{lid}-val"
                        elif txt or val or lbl:
                            compiled_lines.append(
                                NotebookLine(
                                    id=lid,
                                    text=(txt or val or lbl)[:64],
                                    color=color,
                                    bold=bold,
                                    underline=underline,
                                )
                            )
                            arrow_source_id = lid

                def _has_exact_screen_val(val_str: str, blob: str) -> bool:
                    core = self._norm(val_str.split(" (")[0])
                    if not core:
                        return False
                    return bool(re.search(r"(?<![\da-z])" + re.escape(core) + r"(?![\da-z])", blob))

                # Pour une alerte ou la carte Sécurité : si le LLM n'a mis que des paires label/value hors-sujet, passe en puces pédagogiques HeyClicky !
                if (
                    first_role in {"alert", "security"}
                    and not used_explicit_node_ids
                    and llm_payload.get("notebook_lines") is None
                    and compiled_lines
                    and all(ln.label and ln.value for ln in compiled_lines)
                ):
                    if first_role == "alert":
                        nb_title = "Pourquoi cette alerte ?"
                        bullets = [
                            "• Nouveau contact : jamais utilisé avant",
                            "• Un chiffre erroné = argent perdu",
                            "→ Relis chaque chiffre du numéro",
                        ]
                        b_col = "yellow"
                    else:
                        nb_title = "Éviter une arnaque"
                        bullets = [
                            "• Vérifie toujours le nom du bénéficiaire",
                            "• Contrôle chaque chiffre du numéro",
                            "→ Envoie seulement si tu connais la personne",
                        ]
                        b_col = "green"
                    compiled_lines = [
                        NotebookLine(id="nb-l1", text=bullets[0], color=b_col),
                        NotebookLine(id="nb-l2", text=bullets[1], color="red" if first_role == "alert" else None),
                        NotebookLine(divider=True),
                        NotebookLine(id="nb-l3", text=bullets[2], color=b_col, bold=True, underline=True),
                    ]
                    arrow_source_id = "nb-l3"

                # Si un petit LLM a rempli le carnet avec d'autres chiffres que ceux de la cible (ex: Total au lieu de Frais)
                if (
                    grounded_facts
                    and first_role not in {"alert", "security"}
                    and not used_explicit_node_ids
                    and llm_payload.get("notebook_lines") is None
                ):
                    rendered_blob = self._norm(" ".join(f"{ln.label or ''} {ln.value or ''} {ln.text or ''}" for ln in compiled_lines))
                    has_grounded_val = any(_has_exact_screen_val(val, rendered_blob) for _, val in grounded_facts)
                    if not has_grounded_val:
                        compiled_lines = []
                        for idx, (lbl, val) in enumerate(grounded_facts[:2]):
                            lid = f"nb-l{idx + 1}"
                            s_lbl = self._safe_text_for_harness(lbl, screen_context, kb_terms, fallback=lbl)[:32]
                            s_val = self._safe_text_for_harness(val, screen_context, kb_terms, fallback=val)[:36]
                            is_free = bool(re.search(r"(?:^|\b)0\s*fcfa\b", s_val.lower())) or "gratuit" in s_val.lower()
                            compiled_lines.append(
                                NotebookLine(
                                    id=lid,
                                    label=s_lbl,
                                    value=s_val,
                                    color="green" if is_free else accent_color,
                                    bold=True,
                                )
                            )
                            arrow_source_id = f"{lid}-val"

                # Ajoute le séparateur + ligne d'action HeyClicky si le tableau n'a que des paires label/value
                if (
                    compiled_lines
                    and not used_explicit_node_ids
                    and llm_payload.get("notebook_lines") is None
                    and len(compiled_lines) <= 3
                    and all(ln.label and ln.value for ln in compiled_lines)
                ):
                    compiled_lines.append(NotebookLine(divider=True))
                    fact0_val = grounded_facts[0][1].lower() if grounded_facts else ""
                    is_free_fee = bool(re.search(r"(?:^|\b)0\s*fcfa\b", fact0_val)) or "gratuit" in fact0_val
                    has_amount_in_lines = any(
                        extract_amounts(f"{ln.label or ''} {ln.value or ''} {ln.text or ''}")
                        for ln in compiled_lines
                    )
                    if valid_highlights and valid_highlights[0].get("style") == "frame":
                        footer_txt = "→ Appuie sur ce bouton"
                        footer_col = "green"
                    elif len(valid_highlights) >= 2 and any(k in q_norm for k in ("nom", "numero", "beneficiaire", "telephone")):
                        footer_txt = "→ Compare nom et numéro"
                        footer_col = "yellow"
                    elif is_free_fee:
                        footer_txt = "→ Aucun frais sur ce transfert"
                        footer_col = "green"
                    elif "solde" in q_norm:
                        footer_txt = "→ Montant disponible sur ton compte"
                        footer_col = "green"
                    elif any(k in q_norm for k in ("transaction", "historique", "operation")):
                        footer_txt = "→ Regarde tes opérations récentes"
                        footer_col = "yellow"
                    elif len(valid_highlights) >= 2 and has_amount_in_lines:
                        footer_txt = "→ Vérifie ces deux montants"
                        footer_col = "yellow"
                    elif any(k in q_norm for k in ("c'est quoi", "cest quoi", "app", "safinum", "quoi", "sert")):
                        footer_txt = "→ Voici les infos de l'écran"
                        footer_col = "green"
                    elif len(valid_highlights) >= 2:
                        footer_txt = "→ Vérifie ces deux informations"
                        footer_col = "yellow"
                    else:
                        footer_txt = "→ Vérifie bien cette info"
                        footer_col = accent_color
                    compiled_lines.append(
                        NotebookLine(
                            id="nb-l-act",
                            text=footer_txt,
                            color=footer_col,
                            bold=True,
                            underline=True,
                        )
                    )
                    if not arrow_source_id:
                        arrow_source_id = "nb-l-act"

        remaining_visual_budget = 3
        first_node_id = valid_highlights[0]["node_id"] if valid_highlights else None

        # Décide entre Chorégraphie avec Carnet vs Flux d'Action Pur (2 cibles -> bouton CTA)
        raw_spoken_after = str(llm_payload.get("spoken_after") or "").strip()
        spoken_after = self._safe_text_for_harness(raw_spoken_after, screen_context, kb_terms, fallback="")
        is_action_flow = (
            not used_explicit_node_ids
            and llm_payload.get("notebook_lines") is None
            and len(valid_highlights) == 2
            and valid_highlights[1].get("style") == "frame"
            and any(k in q_norm for k in ("comment", "etape", "suivant", "coch", "confirmer", "envoyer", "fais quoi"))
        )

        if is_action_flow:
            # Chorégraphie fidèle à s1-lancer-transfert / s3-cocher-et-continuer : box(1) -> arrow(1->2) -> frame(2)
            t1 = valid_highlights[0]
            t2 = valid_highlights[1]
            sb.draw(t1["style"], "v-mark-1", t1["node_id"], color=t1.get("color", default_color), duration_ms=640, run_after_ms=0, label=t1.get("label"))
            sb.arrow("a-flow", t1["node_id"], t2["node_id"], color="ink", duration_ms=680, run_after_ms=1100)
            sb.draw("frame", "v-mark-2", t2["node_id"], color="red", duration_ms=520, run_after_ms=1950, label=t2.get("label") or "Appuie ici")
            follow_txt = spoken_after or f"Ensuite, appuie sur {usable_nodes[t2['node_id']].text} pour continuer."
            follow_txt = self._safe_text_for_harness(follow_txt, screen_context, kb_terms, fallback="")
            if follow_txt:
                sb.speak("llm_follow", follow_txt, lang, 1950)
            sb.clear(7200)
            return sb.actions

        if nb_title and compiled_lines:
            sb.notebook(
                "nb-guide",
                nb_title[:48],
                compiled_lines,
                anchor_id=first_node_id,
                run_after_ms=0,
            )
            remaining_visual_budget -= 1  # Reste 2 marques visuelles

        # 3. Tracés visuels (<= 3 marques au total)
        cursor_ms = 1400 if (nb_title and compiled_lines) else 250
        arrow_drawn = False
        spoken_after_emitted = False

        # Avec Carnet + 2 vraies cibles (ex: Nom ET Numéro), on dessine les 2 boîtes (notebook + box1 + box2 = 3)
        use_dual_highlight = (
            not used_explicit_node_ids
            and llm_payload.get("notebook_lines") is None
            and len(valid_highlights) >= 2
            and remaining_visual_budget == 2
        )

        # Voix de guidage contextuelle au moment du tracé (corrige aussi si le petit LLM a recopié un exemple générique hors-sujet)
        generic_after = {
            "regarde juste ici sur ton ecran",
            "regarde exactement ici sur ton ecran",
            "regarde ici sur ton ecran",
            "appuie sur ce bouton pour continuer",
            "verifie bien ce chiffre ici",
        }
        if (
            not used_explicit_node_ids
            and valid_highlights
            and llm_payload.get("notebook_lines") is None
            and getattr(self.llm, "last_engine", None) != "heuristic"
        ):
            first_nid = valid_highlights[0]["node_id"]
            first_meta = node_meta.get(first_nid, {})
            f_role = first_meta.get("role", "text")
            f_style = valid_highlights[0].get("style")
            sa_n = self._norm(spoken_after)
            asks_benef = any(k in q_norm for k in ("beneficiaire", "destinataire", "numero", "telephone", "nom", "qui", "arnaqu", "securite"))
            has_amount_hl = any(
                extract_amounts(usable_nodes[h["node_id"]].text or "")
                for h in valid_highlights
                if h["node_id"] in usable_nodes
            ) or any(extract_amounts(val) for _, val in grounded_facts)
            is_mismatch = (
                not sa_n
                or sa_n in generic_after
                or ("bouton" in sa_n and f_style != "frame" and f_role != "button")
                or ("chiffre" in sa_n and (f_style == "frame" or f_role in {"button", "security"}))
                or ("case a cocher" in sa_n and f_role != "checkbox")
                or (("beneficiaire" in sa_n or "numero" in sa_n) and f_role != "security" and not asks_benef and screen_context.screen_hint not in {"beneficiary", "recap"})
            )
            if is_mismatch:
                if len(valid_highlights) >= 2 and use_dual_highlight:
                    if any(k in q_norm for k in ("nom", "numero", "beneficiaire", "telephone")):
                        cand_after = "Contrôle d'abord le nom puis chaque chiffre du numéro encadré."
                    elif has_amount_hl:
                        cand_after = "Compare ces deux montants encadrés avant de confirmer."
                    elif grounded_facts:
                        lbl0, val0 = grounded_facts[0]
                        cand_after = f"Tu peux lire ici : {lbl0} : {val0}."
                    else:
                        cand_after = "Regarde ces deux informations encadrées sur ton écran."
                elif f_style == "frame" or f_role == "button":
                    btn_name = first_meta.get("gloss_only") or usable_nodes[first_nid].text or "ce bouton"
                    cand_after = f"Appuie exactement ici sur « {btn_name[:28]} »."
                elif f_role == "checkbox":
                    cand_after = "Coche d'abord cette case puis appuie sur le bouton pour continuer."
                elif f_role == "alert":
                    cand_after = "Lis bien cet avertissement jaune puis vérifie le numéro avant d'envoyer."
                elif f_role == "security":
                    cand_after = "Retiens ce réflexe : vérifie toujours le nom et le numéro avant d'envoyer."
                elif grounded_facts:
                    lbl0, val0 = grounded_facts[0]
                    cand_after = f"Tu peux lire ici : {lbl0} : {val0}."
                else:
                    cand_after = "Regarde exactement l'élément entouré ici."
                spoken_after = self._safe_text_for_harness(cand_after, screen_context, kb_terms, fallback="Regarde exactement ici.")

        for idx, h in enumerate(valid_highlights):
            if remaining_visual_budget <= 0:
                break
            nid = str(h["node_id"])
            style = str(h.get("style") or default_style).lower()
            if style not in ALLOWED_HIGHLIGHT_STYLES:
                style = "box"
            color = str(h.get("color") or default_color).lower()
            if color not in ALLOWED_COLORS:
                color = "yellow"
            elif color in {"ink", "green"} and not used_explicit_node_ids:
                color = "yellow"  # Jaune feutre contrasté sur fonds sombres (Safinum) sans vert ni encre sombre quasi invisible
            label = str(h.get("label") or "").strip()[:24] if style == "frame" and h.get("label") else None
            arrow_pref = h.get("arrow_from_notebook")
            wants_arrow = (False if use_dual_highlight else (idx == 0)) if arrow_pref is None else bool(arrow_pref)

            if wants_arrow and arrow_source_id and not arrow_drawn and remaining_visual_budget >= 2:
                sb.arrow("a-guide", arrow_source_id, nid, color=color, duration_ms=620, run_after_ms=cursor_ms)
                arrow_drawn = True
                remaining_visual_budget -= 1
                if spoken_after and not spoken_after_emitted:
                    sb.speak("llm_follow", spoken_after, lang, cursor_ms)
                    spoken_after_emitted = True
                cursor_ms += 780

            if remaining_visual_budget <= 0:
                break
            sb.draw(
                style,
                f"v-mark-{idx + 1}",
                nid,
                color=color,
                duration_ms=600,
                run_after_ms=cursor_ms,
                label=label,
            )
            remaining_visual_budget -= 1
            if spoken_after and not spoken_after_emitted and (not use_dual_highlight or idx == len(valid_highlights[:2]) - 1):
                sb.speak("llm_follow", spoken_after, lang, cursor_ms)
                spoken_after_emitted = True
            cursor_ms += 800

        if spoken_after and not spoken_after_emitted:
            sb.speak("llm_follow", spoken_after, lang, max(cursor_ms, 1200))

        clear_at = max(cursor_ms + 4500, 7800)
        sb.clear(clear_at)
        return sb.actions

    @staticmethod
    def _get_turn_cache_key(transcript: Transcript, screen_context: ScreenContext) -> tuple[int, str, str] | None:
        if not screen_context.nodes or not transcript.text:
            return None
        node_sig = hash(tuple((n.node_id, n.text, n.clickable) for n in screen_context.nodes if n.text))
        return (node_sig, transcript.lang or "fr", transcript.text.strip().lower())

    def candidate_actions(
        self, transcript: Transcript, screen_context: ScreenContext
    ) -> list[ActionMessage]:
        """Délègue la décision complète au LLM open-weight en lui fournissant le ScreenContext réel."""
        if self._is_out_of_scope_question(transcript.text, screen_context):
            return self._build_out_of_scope_actions(transcript, screen_context)

        # 1. Cache mémoire ultra-rapide (<1ms si même écran et même question)
        cache_key = self._get_turn_cache_key(transcript, screen_context)
        if cache_key and cache_key in self._turn_cache:
            return self._turn_cache[cache_key]

        prompt = self._build_llm_prompt(transcript, screen_context)
        llm_payload = self.llm.generate(
            prompt,
            options={"temperature": 0.0, "num_predict": 10, "num_thread": 2, "stop": ["\n", ";"]},
            format_type=None,
        )

        # Compatibilité avec l'ancien format mocké par les tests unitaires existants
        if (
            isinstance(llm_payload, dict)
            and llm_payload.get("intent") == "check_balance"
            and not llm_payload.get("spoken")
        ):
            actions = self._compile_legacy_check_balance(llm_payload, transcript, screen_context)
        else:
            actions = self._compile_llm_plan(
                llm_payload if isinstance(llm_payload, dict) else {}, transcript, screen_context
            )

        if cache_key:
            self._turn_cache[cache_key] = actions
            if len(self._turn_cache) > 256:
                self._turn_cache.pop(next(iter(self._turn_cache)))

        return actions

    def handle_turn(
        self, transcript: Transcript, screen_context: ScreenContext
    ) -> list[ActionMessage]:
        """Orchestre la réception d'un tour : génération par LLM (M2.1) + validation par le harnais (M2.2)."""
        self.last_screen_context = screen_context
        raw_actions = self.candidate_actions(transcript, screen_context)
        return validate_action_stream(raw_actions, screen_context, self.kb.terms)
