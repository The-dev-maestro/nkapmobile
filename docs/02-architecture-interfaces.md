# nkapmobile — Architecture & contrats d'interfaces
### v1 · 8 nov. 2026 · LE document contrat de l'équipe

> Règle du document : **chaque module se code contre ce document seul.** Tout
> échange entre modules passe par un payload défini ici. Changer un payload =
> proposer une modification versionnée de ce doc (v1.1, v1.2…) — jamais à l'oral.

---

## 0. Vue d'ensemble et transport

```
┌────────────────────────── APPAREIL (Android) ──────────────────────────┐
│                                                                        │
│  nkap-app                                                              │
│  ├── M4 CONTEXT PROVIDER (AccessibilityService)                        │
│  │     arbre UI réel → ScreenContext (I5)                              │
│  ├── M1 MOTEUR DE RENDU (core KMP + couche Android)                    │
│  │     ActionStream → dessin à l'écran (I4)                            │
│  └── client session (WS, audio in/out, cache)                          │
└───────────────┬────────────────────────────────────────────────────────┘
                │  WebSocket unique (JSON texte + trames binaires audio)
                ▼
┌────────────────────────── SERVEUR (AWS) ──────────────────────────────┐
│  gateway (WS session, routage, enveloppe commune)                      │
│    ├── M2 CERVEAU : LLM (Bedrock) + harnais (validateur + scheduler)   │
│    │     Entrées : Transcript (I1-out) + ScreenContext (I5) + KB (M5)  │
│    │     Sortie  : ActionStream (I3)                                   │
│    ├── M3 VOIX : /stt (I1) · /tts (I2)                                 │
│    └── M5 KB : dossier par entreprise (RAG : inventaire UI,            │
│         lexique verrouillé, banque de phrases validées, FAQ)           │
└────────────────────────────────────────────────────────────────────────┘
```

**Décisions transport (v1, actées) :**
- **Une seule WebSocket** par session (JSON + binaire audio). Repli dégradé HTTP impossible : hors ligne = mode local (caption + dessin sur phrases mises en cache, pas de LLM).
- **Audio v1 = clips push-to-talk** (l'utilisateur maintient la bulle, parle, relâche). Le streaming continu avec VAD = v2 — le format des trames ne change pas.
- **Le serveur ne connaît jamais les pixels.** Toutes les cibles visuelles sont des `node_id` issus du ScreenContext ; l'appareil résout les coordonnées au moment d'exécuter (l'UI a pu bouger).
- **Horloge du tour** : M3 renvoie la durée de chaque synthèse vocale → M2 calcule un planning en `run_after_ms` relatif au début de chaque segment vocal → M1 exécute sans prendre de décision temporelle. v2 (streaming) : mêmes payloads, émis progressivement.

**Enveloppe commune** — tout message JSON a :

```json
{ "type": "…", "session_id": "s_9f2", "turn_id": "t_17", "ts": 1699450000123 }
```
`turn_id` = un tour question→réponse. Tout ce qui arrive avant le `turn_end` appartient au même tour.

---

## 1. Cycle de vie d'une session (séquence complète)

```
APPAREIL                         SERVEUR
   │ ── hello ────────────────────►│
   │ ◄── hello_ack ────────────────│
   │ ── screen_context ───────────►│   (à chaque changement de fenêtre/écran)
   │                               │
   │ ══ user appuie, parle ══      │
   │ ── audio_start ──────────────►│
   │ ── audio_chunk (bin) ×N ─────►│
   │ ── audio_end ────────────────►│
   │ ◄── transcript ───────────────│   (I1 : STT M3)
   │ ◄── action(speak) ────────────│   (I3 : le cerveau streame ses actions)
   │ ◄── audio_out(url, speak_id) ─│   (I2 : TTS M3)
   │ ◄── action(circle …) ─────────│   exécution différée de run_after_ms
   │ ◄── action(frame …) ──────────│
   │ ◄── turn_end ─────────────────│
   │                               │
   │ ══ app rend la main à l'UI ══ │
```

**Répétition proactitve (v2, hors périmètre du 14 nov.)** : le serveur peut envoyer `action(caption)` + `speak` sans question (ex. détection d'un message d'erreur à l'écran) — le format ci-dessous le permet déjà, le déclencheur n'existe pas en v1.

---

## 2. I5 — ScreenContext (M4 → serveur)

**Émis** : à la connexion, puis à chaque changement de fenêtre/activité, et à la demande (`context_request`).

```json
{
  "type": "screen_context",
  "session_id": "s_9f2",
  "turn_id": null,
  "ts": 1699450000123,
  "app": { "package": "cm.demo.fintech", "activity": "HomeActivity" },
  "screen_hint": "home",
  "nodes": [
    {
      "node_id": "n_01",
      "path": "root/scroll/balance_card",
      "cls": "android.view.ViewGroup",
      "text": "Solde disponible 42 500 FCFA",
      "content_desc": null,
      "clickable": false,
      "password": false,
      "bounds": [16, 115, 344, 223],
      "tone": "unknown"
    },
    {
      "node_id": "n_02",
      "path": "root/scroll/balance_card/amount",
      "cls": "android.widget.TextView",
      "text": "42 500 FCFA",
      "bounds": [90, 160, 270, 200],
      "tone": "unknown"
    }
  ]
}
```

| Champ | Règle |
|---|---|
| `nodes[]` | ≤ 200 nœuds visibles porteurs de texte ou cliquables ; ordre du parcours de l'arbre (implicite : hiérarchie) |
| `node_id` | stable au sein d'un écran : `n_01…` régénéré à chaque snapshot ; le serveur référence le snapshot courant |
| `bounds` | `[left, top, right, bottom]` **pixels écran** (window coords) |
| `tone` | `"light" \| "dark" \| "unknown"` — l'arbre d'accessibilité **ne donne pas la couleur de fond** → `unknown` par défaut. Le moteur de rendu dessine alors au **trait double contour** (lisible partout) et `write` prend un `backing: "paper"` |
| Sécurité | tout nœud `password=true` ou champ de saisie (`EditText`) → **exclu** ; texte jamais lu pour ces nœuds |
| Poids | snapshot ≤ 30 Ko compressé |

**Acceptation M4** : snapshot ≤ 300 ms ; rafraîchi sur changement de fenêtre ; zéro champ de saisie transmis ; testé sur 3 apps (notre démo, une banque réelle quelconque, Chrome).

---

## 3. I1 — STT (M3, `POST /stt` interne serveur)

```json
// Requête (serveur interne, auth par token service)
{ "audio_b64": "…(opus/mp4)…", "lang_hint": "ewo", "sample_rate": 16000 }
// Réponse
{ "text": "Ndɛn wɔ́g í bɔ́l ?", "lang": "ewo", "duration_s": 2.4, "conf": 0.81 }
```
- `text` **brut, sans ponctuation imposée** ; `lang` peut corriger le hint.
- Le transcript part ensuite au cerveau dans le message WS `transcript` (mêmes champs + enveloppe).
- **Acceptation M3-STT** : WER ≤ 35 % sur notre jeu de 30 phrases-test ewondo enregistrées par le locuteur (jeu = livrable, voir §9).

## 4. I2 — TTS (M3, `POST /tts` interne serveur)

```json
// Requête
{ "text": "Solde wɔ́g á 42 500 FCFA.", "lang": "ewo", "mode": "bank", "phrase_key": "balance_answer", "vars": { "amount": "42 500 FCFA" } }
// Réponse
{ "audio_url": "https://cdn…/s_9f2_t17_a3.opus", "duration_ms": 2350, "mode_used": "bank", "cache_hit": true }
```
- **`mode: "bank"`** (défaut) : la phrase DOIT exister dans `phrases.json` validée (M5) ; sinon M3 répond 422 `phrase_not_validated` → le harnais reformule via un template validé.
- **`mode: "neural"`** (repli) : `mms-tts-ewo` ; `mode_used` informe le serveur de ce qui a réellement joué.
- `audio_url` : Opus 48 kbps mono, **mis en cache CloudFront/S3** — l'appareil télécharge et joue.
- **Acceptation M3-TTS** : 100 % des `phrase_key` des templates M2 couverts par la banque ; neural < 2 s de latence.

## 5. I3 — ActionStream (cerveau → appareil)

Chaque geste = un message `action`. **Vocabulaire fermé de 9 types** — le validateur du harnais rejette tout le reste.

### Cibles

```json
"target": { "node_id": "n_01", "dx": 0, "dy": -34 }        // ancre (résolue à l'exécution)
"target": { "free": { "x": 0.5, "y": 0.18 } }              // position normalisée 0..1
```
L'appareil re-résout `node_id` → bounds **au moment d'exécuter** (scroll-support). Nœud disparu → le geste est sauté silencieusement (jamais d'erreur visible).

### Les 9 types (examples complets)

```json
{ "type": "action", "session_id": "s_9f2", "turn_id": "t_17", "ts": 1699450002100,
  "seq": 1, "speak_seg": 0, "run_after_ms": 0,
  "action": { "t": "speak", "id": "spk_1", "text": "Solde wɔ́g á 42 500 FCFA.",
              "lang": "ewo", "mode": "bank", "phrase_key": "balance_answer" } }

{ "type": "action", "seq": 2, "speak_seg": 0, "run_after_ms": 200,
  "action": { "t": "circle", "id": "c_1", "target": { "node_id": "n_01" },
              "color": "ink", "duration_ms": 700 } }

{ "type": "action", "seq": 3, "speak_seg": 0, "run_after_ms": 900,
  "action": { "t": "write", "id": "w_1", "text": "42 500 FCFA",
              "target": { "node_id": "n_01", "dy": -66 }, "size": 27,
              "color": "ink", "backing": "paper", "per_letter_ms": 55 } }

{ "type": "action", "seq": 4, "speak_seg": 0, "run_after_ms": 0,
  "action": { "t": "caption", "text": "Solde wɔ́g á 42 500 FCFA.", "sub_fr": "Votre solde : 42 500 FCFA" } }

{ "type": "action", "seq": 5, "action": { "t": "underline", "id": "u_1",
  "target": { "node_id": "n_07" }, "color": "yellow", "duration_ms": 450 } }

{ "type": "action", "seq": 6, "action": { "t": "arrow", "id": "a_1",
  "from": { "node_id": "n_01", "dx": 110, "dy": 30 }, "to": { "node_id": "n_04" },
  "color": "ink", "duration_ms": 850 } }

{ "type": "action", "seq": 7, "action": { "t": "frame", "id": "f_1",
  "target": { "node_id": "n_09" }, "label": "Poussa ici" } }

{ "type": "action", "seq": 8, "action": { "t": "hide", "id": "w_1" } }
{ "type": "action", "seq": 9, "action": { "t": "clear" } }
```

| Champ | Règle |
|---|---|
| `seq` | ordre strict croissant par tour — l'appareil exécute dans l'ordre d'arrivée compatible |
| `speak_seg` + `run_after_ms` | moment d'exécution relatif au **début de lecture** du n-ième segment vocal du tour. `speak_seg: null` (ou absent) = dès réception |
| `color` | `"ink" \| "yellow" \| "red"` — sémantique verrouillée : ink=expliquer, yellow=souligner, red=agir/alerter |
| `text` de `write` | montants/noms/bénéficiaires **recopiés à l'identique du ScreenContext** — le validateur rejette toute altération |
| Limites | ≤ 3 marques simultanées, ≤ 1 `frame` par tour, durée totale conseillée ≤ 9 s |

### Validation côté harnais (règles exécutées avant envoi)
1. Schéma : types fermés, champs requis, cibles existantes dans le ScreenContext courant.
2. Montants : toute chaîne de type montant (`/[\d\s.,]+ *(FCFA|francs?)/i`) dans `write`/`speak` doit exister à l'identique dans le contexte écran ou le lexique — sinon rejet + reformulation.
3. Budget : si > 3 marques vivantes → `hide` automatique des plus anciennes (le scheduler peut l'insérer).
4. Phrases vocales : `mode: "bank"` exige `phrase_key` validé (M5) ; sinon passage forcé en template validé.

**Acceptation M2** : 95 % des flux produits sur notre jeu de questions-test passent le validateur sans retouche ; latence transcript→première action ≤ 1,5 s.

## 6. I4 — Rendu (M1, interne appareil)

Entrée = ActionStream. Contrat observable :
- 9 types rendus ; tracé progressif (dessin, jamais apparition sèche sauf `frame` ≤ 120 ms).
- Sync : exécution à `run_after_ms` ± 150 ms du début du segment audio.
- `tone: unknown` → trait double-contour (encre claire + liseré sombre), `write` → `backing` forcé `paper`.
- 50 fps pendant l'animation ; aucun crash sur nœud disparu ; tout s'efface au `clear` ≤ 300 ms.
- Bulle assistant (push-to-talk) + sous-titres `caption` (Andika), jamais au-dessus du chrome système.

## 7. M5 — KB entreprise (format dossier, consommé par M2)

```
kb/<entreprise>/
  manifest.json      { "name": "demo-fintech", "lang": ["fr","ewo"], "version": 3 }
  ui_inventory.json  { "screens": { "home": { "purpose_fr": "…", "purpose_ewo": "…",
                         "components": { "balance_card": {"gloss": "solde = ndɛn"} } } } }
  lexicon.json       { "solde": "ndɛn", "frais": "mbug", … }   // verrouillé, 150+ entrées
  phrases.json       { "balance_answer": { "ewo": "Solde wɔ́g á {amount}.",
                        "fr": "Votre solde est de {amount}.", "audio": "opus/…",
                        "validated_by": "locuteur-1", "validated_at": "…" } }  // 60+
  faq.md, tariffs.md
```
Le RAG (retrieval sur lexique + inventaire + FAQ) est interne à M2 ; **seul le format dossier est le contrat**. Ajouter une entreprise = créer un dossier, zéro code.

## 8. Parcours imposés → contrat d'équipe

Les 5 parcours du sujet + le contenu inédit, chacun = une séquence complète exigée en démo :

| # | Parcours | Question type (ewondo) | Marques attendues (min.) |
|---|---|---|---|
| P1 | Consultation solde | « Quel est mon solde ? » | circle + write(montant) + speak(bank) |
| P2 | Frais d'une opération | « C'est quoi ces frais ? » | underline + write(frais) |
| P3 | Préparation transfert | « Comment envoyer à ma sœur ? » | circle + arrow + frame(CTA) |
| P4 | Récapitulatif avant confirmation | « Récapitule-moi » | underline ×2 (montant, frais) + write(total) |
| P5 | Erreur / avertissement sécurité | « Ce message, c'est quoi ? » | frame rouge + speak(alerte validée) |
| P6 | **Contenu inédit** (injecté par le jury) | message jamais vu | même grammaire — le LLM compose, la banque vocale est contournée via neural + phrase simple validée générique |

**Critère d'intégration équipe (11 nov.)** : P1→P5 enchaînés sans restart, en ewondo, sur l'app démo. P6 testé avec 10 messages inédits maison.

## 9. Jeux de test (livrables partagés, propriétaire M3)

- `fixtures/stt-test-30.ewo` : 30 phrases enregistrées (locuteur) → WER STT.
- `fixtures/questions-demo.json` : les questions des 5 parcours (audio + texte).
- `fixtures/messages-inedits.json` : 10 messages surprises pour P6.
- `fixtures/contexts/` : ScreenContext JSON enregistrés (permettent à M2 et M1 de travailler **sans** appareil ni serveur).

## 10. Qui code quoi (contremarque du §6 du cadrage)

| Propriétaire | Modules | « Terminé » signifie |
|---|---|---|
| **Membre 1** | M1 + M4 + nkap-app | §6 + §2 acceptation ; P1-P6 s'affichent depuis un flux `fixtures/actions-*.json` rejoués |
| **Membre 2** | gateway + M2 + M5 | §5 acceptation ; sur `fixtures/questions-demo.json` + `fixtures/contexts/` → flux validés sans appareil |
| **Membre 3** | M3 + fixtures + locuteur | §3-§4 acceptation ; banque complète + 30 phrases-test livrées |

> Grâce aux `fixtures/`, **aucun module n'attend un autre** : chacun se teste contre des données figées issues de ce contrat.

## 11. Ouverts (à trancher avant le 10)

1. `screen_hint` (M4) : heuristique locale simple vs classifié par M2 — v1 : heuristique sur `activity` + premiers textes.
2. `caption.sub_fr` : sous-titre bilingue permanent ou ewondo seul ? (démo jury : bilingue recommandé).
3. Auth appareil↔serveur : token statique v1 (démonstration), vrai device-auth post-hackathon.
