# HANDOFF — État du projet nkapmobile
### Dernière mise à jour : 8 nov. 2026 · session ZCode (GLM) avec membre 1

> **Comment reprendre** : dans une nouvelle session ZCode, dire simplement
> *« Lis HANDOFF.md à la racine du repo nkapmobile »* — puis préciser la tâche du
> moment (voir §9). Tous les chemins sont absolus sur la machine du membre 1.

---

## 1. Mission

**nkapmobile** — couche d'accessibilité linguistique pour app fintech Android :
un AccessibilityService lit l'écran de **n'importe quelle app** (zéro modification),
un LLM (Bedrock) streame des **actions visuelles** (cercle/écriture/soulignement/
cadre/flèche/caption façon « annotation manuscrite ») synchronisées avec une
**voix ewondo**, par-dessus l'UI réelle.

- **Événement** : SAFINUM Innovate Challenge, Palais des Congrès Yaoundé, 26-28 nov. 2026
  (prix 1er : 2 500 000 FCFA). Sponsor hackathon : Wave.
- **Échéance immédiate** : prototype de **présélection à remettre le 14 nov. 2026**.
  Livrables : description + prototype + vidéo 3 min + note technique + méthode de
  validation linguistique. Parcours imposé : solde, frais, transfert, récapitulatif,
  erreur/sécurité + **contenu inédit injecté par le jury**. Critères : 100 pts
  (fonctionnement 25, intégration 20, sécurité 20, UX 15, inédit 10, doc 10).
  **Facteur éliminatoire** : erreur linguistique modifiant un sens financier.

## 2. Équipe

| Membre | Module | Statut |
|---|---|---|
| **membre 1 (utilisateur, GitHub `deiryl237`)** | M1 moteur de rendu + M4 contexte d'écran + vision artistique | apprend Kotlin via Antigravity + toolkit Manware (LEARN.md) |
| membre 2 | M2 cerveau (harnais LLM) + M5 KB/RAG + AWS | nom inconnu — à confirmer |
| membre 3 | M3 voix (STT/TTS) + fixtures + recrutement locuteur | nom inconnu — à confirmer |

**Aucun locuteur ewondo dans l'équipe** — recrutement d'un relecteur à distance en cours
(pistes : NABU/IHS Cameroon, Université de Yaoundé I, ANACLAC/CABTAL, paroisses).
Règle absolue : **aucune phrase ewondo non validée ne sort en démo** (facteur éliminatoire).

## 3. Décisions actées (avec les débats tranchés)

1. **Repartir de zéro** — le PoC ne sert que de capital de connaissances (§6) et de
   référence de lecture (archivé, §5).
2. **Architecture 5 modules / 5 interfaces** (docs/02) : M1 rendu · M2 cerveau+harnais ·
   M3 voix · M4 contexte (AccessibilityService) · M5 KB entreprise.
3. **Flux d'actions, ni script one-shot ni tools** : le LLM streame un seul flux où
   `speak` et les gestes s'entrelacent (le dessin suit la voix naturellement).
   v1 = blocs par phrase, v2 = streaming token — même interface.
4. **KB entreprise = RAG** (dossier par entreprise), PAS de fine-tuning avant la finale.
5. **Moteur = Kotlin natif Android** : AccessibilityService + overlay
   `TYPE_ACCESSIBILITY_OVERLAY` (prouvé par spike) ; `core` KMP prévu pour port iOS
   (SDK in-app SwiftUI) plus tard.
6. **Ewondo complet** : STT = fine-tune Whisper sur Common Voice v27 ewo (14,4 h CC0) ;
   TTS = banque ~60 phrases validées (primaire) + `mms-tts-ewo` (repli libre, CC-BY-NC) ;
   cerveau contraint par lexique verrouillé (le LLM compose, n'invente pas).
7. **Cloud AWS** (crédits équipe, ~100-300 $) : Bedrock (cerveau) + EC2 GPU spot
   (fine-tune puis inférence démo). Règles : aucune instance laissée allumée,
   alarmes facturation 60/80 $, vérifier éligibilité Bedrock + expiration des crédits.
   Le laptop local reste le repli complet (le cloud n'est pas un chemin critique).
8. **Git** : UN seul repo `deiryl237/nkapmobile` — branches `master` (livrables) /
   `dev` (intégration) / `perso/<pseudo>-<module>`. Jamais de push direct master.
   Règle ≤ 3 marques simultanées, montants jamais reformulés (validé par le harnais).

## 4. Carte des fichiers

```
C:\Users\UltraBook 3.1\Desktop\nkapmobile\        ← LE REPO GIT (branche active : perso/deiryl-moteur-rendu)
├── HANDOFF.md                    ← ce fichier
├── LEARN.md                      ← curriculum du membre 1 (7 leçons, C#→Kotlin)
├── app\                          ← (vide) terrain de la Leçon 1
├── moteur-rendu\  (sur dev+)     ← zone M1 : LEARN.md + learning/ + app déplacés ici sur dev
├── cerveau\ voix\ fixtures\      ← zones membres 2-3 (vides, .gitkeep)
├── docs\
│   ├── 01-cadrage.md             ← cadrage v1 (exigences mappées, archi, plan J-7, budget AWS)
│   ├── 02-architecture-interfaces.md  ← LE CONTRAT : payloads I1-I5, 9 actions, parcours P1-P6
│   ├── 03-git-workflow.md        ← règles branches + cheat-sheet par membre
│   └── learning-toolkit-readme.md
├── .agents\                      ← toolkit Manware pour Antigravity (learning-companion)
├── learning\                     ← journal du membre 1 (concepts/mistakes/questions/review)
└── captures\                     ← preuves (spike, signature v2, compositions)

C:\Users\UltraBook 3.1\Desktop\projets\architecture logicielle\
├── archive-spike-context-overlay\   ← SPIKE prouvé (AccessibilityService + overlay) — lecture seule
├── hackathon-safinum\               ← ANCIEN PoC (archivé, code abandonné) + docs de recherche :
│     ├── recherche-langues-camerounaises.md   (corpus/stt/tts/licences des langues, URLs vérifiées)
│     ├── concept-experience.md                (concept v2 « le tableau », règles qualité)
│     ├── architecture-couche.md, pitch-candidature.md, checklist-pre-hackathon.md
└── outils\ plateforme-portefeuilles-wso2\   (hors projet)
```

**Branches Git** : `master` = `dev` = `perso/deiryl-moteur-rendu` (alignées à
76ea36f le 8 nov.). À partir de maintenant : le membre 1 code sur sa branche perso,
merge dans dev quand utilisable ; master ne bouge qu'aux jalons (11/13/14 nov.).

## 5. Environnement technique (machine du membre 1)

- **Téléphone test** : Infinix X6835B, USB, id `0985537349008864`, densité ~2.2
  (720×1640 px, 360×744 dp). Le PoC RN/Expo est mort (décision), plus de serveur Expo.
- **JDK 21** : `C:\Program Files\Java\jdk-21` (JAVA_HOME à exporter dans chaque session bash)
- **Android SDK** : `C:\Users\UltraBook 3.1\AppData\Local\Android\Sdk` (platforms android-34, build-tools 34.0.0)
- **Gradle 8.7** : `C:\Users\UltraBook 3.1\gradle\gradle-8.7\bin\gradle.bat`
- **Build spike** : `cd spike && export JAVA_HOME="C:\Program Files\Java\jdk-21" && ~/gradle/gradle-8.7/bin/gradle.bat assembleDebug`
- **Activation AccessibilityService via adb (XOS exige le nom COMPLET)** :
  `adb shell settings put secure enabled_accessibility_services cm.nkapmobile.spike/cm.nkapmobile.spike.SpikeAccessibilityService`
  puis `adb shell settings put secure accessibility_enabled 1` — vérifier avec `settings get`.
- **pypdf venv** : `C:\Users\UltraBook 3.1\pdfwork\.venv` (extract.py — lire les PDF du challenge)
- **Editeurs** : Antigravity IDE + VS Code installés ; le membre 1 code dans Antigravity
  (toolkit Manware = l'IA n'écrit pas, elle questionne). **ZCode = mentor/testeur** (ne
  code pas non plus les leçons ; lui font : archi, contrats, revues adb, modules des autres).

## 6. Capital de connaissances (leçons à NE PAS réapprendre)

### Technique Android (du spike + PoC)
- **Edge-to-edge** : la racine RN/vue s'étend au-dessus de la fenêtre (origin.y négatif) →
  convertir fenêtre→surface pour toute coordonnée de dessin.
- **Margins sur l'ancre, jamais sur l'enfant** : sinon le nœud mesuré déborde.
- **Overlay sans permission** : `TYPE_ACCESSIBILITY_OVERLAY` + `FLAG_NOT_TOUCHABLE` +
  `FLAG_NOT_FOCUSABLE` + `PixelFormat.TRANSLUCENT`.
- **Filtre sécurité** : `isPassword` / `EditText` jamais dumpés ni dessinés (règle jury).
- **Tone des fonds inconnu via l'arbre d'accessibilité** → trait double-contour
  (encre claire + liseré sombre) et `write` avec backing papier.
- **Activation XOS** : settings put exige le composant complet (voir §5).
- RN 0.88 (si jamais on retourne au PoC) : FormData{uri} cassé → base64.

### Produit / linguistique
- Identité visuelle « le tableau » (issue de l'analyse des démos heyclicky, frames dans
  `~/heyclicky-frames/`) : 6 gestes, 3 encres (ink=expliquer, yellow=souligner, red=agir),
  ≤ 3 marques simultanées, tout se dessine progressivement, sous-titres systématiques,
  police **Andika** (SIL, couvre ɓ/ə/ɔ/ŋ/tons).
- **Corpus** : Common Voice v27 ewo 14,4 h CC0 ; cameroon_bibles (flagship-ai) 60 langues
  CC-BY ; JW300 = risque droits ; MMS = CC-BY-NC ; Whisper ne couvre ni fulah ni ewo
  (fine-tune obligatoire) ; aucun TTS commercial ewo.
- **Précédent produit** : MTN Ouganda (USSD MoMo en luganda). Aucun lexique financier
  ewondo n'existe → le créer est une contribution différenciante.

## 7. Contrats (le document de référence = docs/02)

- I1 STT : `POST /stt {audio_b64, lang_hint} → {text, lang, conf}`
- I2 TTS : `POST /tts {text|phrase_key+vars, mode:bank|neural} → {audio_url, duration_ms}`
- I3 ActionStream (WS) : `ask(audio+screen_context) → transcript → action* → turn_end` ;
  9 types d'actions ; cibles = `node_id` du ScreenContext (jamais de pixels côté serveur) ;
  `run_after_ms` relatif au segment vocal.
- I5 ScreenContext : nœuds `{node_id, path, cls, text, bounds, tone, password}` ≤ 200,
  champs de saisie exclus, ≤ 30 Ko.
- I4 rendu : contrats observables (tracé progressif, sync ±150 ms, pas de crash sur
  nœud disparu, clear ≤ 300 ms).
- **fixtures/** = données de test partagées (actions rejouables, contexts, 30 phrases
  STT, messages inédits) — chacun teste son module sans attendre les autres.

## 8. Historique rapide (pour replacer les débats)

- 4-5 nov. : recherche langues (3 rapports) → ewondo retenu ; concept v2 (« le tableau »)
  écrit après analyse frame par frame des démos heyclicky (v1 « trait doré » rejetée par
  le membre 1).
- 5 nov. : PoC RN/Expo construit + validé sur appareil (pipeline vocal complet) — a
  convaincu l'équipe ; leçon : valider la COMPOSITION, pas seulement les gestes isolés.
- 7-8 nov. : décision de repartir de zéro ; cadrage v1 + contrat d'interfaces rédigés ;
  leçon 6 (gestes) reconnue comme le pont LLM↔rendu ; spike natif prouvé ; repo Git
  d'équipe structuré (master/dev/perso).

## 9. MOTEUR-RENDU-IA (référence complète, branche `ia/moteur-rendu`)

Le 9 nov., une implémentation **complète et validée sur Infinix** du M1+M4 existe dans
`moteur-rendu-ia/` (branche Git `ia/moteur-rendu`, validée sur les parcours P1/P2/P3,
captures dans `captures/engine-kotlin-*.png`) :

- `core/` (Kotlin pur, testable) : protocole 9 actions + ScreenContext (parsing défensif),
  géométrie manuscrite déterministe (tremblé seedé, tracé progressif via PathMeasure),
  règles de composition (≤ 3 marques via LiveMarks, AmountGuard qui rejette tout
  montant altéré — il a déjà bloqué des actions en conditions réelles).
- `service/ScreenReaderService` : M4 (dump arbre → ScreenContext, filtre PIN/EditText,
  snapshot périodique + événements) + gestion des 3 couches overlay (marks/captions/bulle).
- `overlay/` : OverlaySurface (tracé progressif double-contour, write papier lettre par
  lettre, frame coins + étiquette, captions Andika avec fondu), CaptionLayer,
  AssistantBubble (SEULE couche tactile, 140 px bas-droite).
- `session/WsSession` : protocole WS du contrat (hello, screen_context, ask audio b64,
  action, turn_end) — URL configurable dans les prefs (`nkap` → `ws_url`).
- `demo/` : DemoDirector (fixtures embarquées, cibles par `match_text` — extension
  offline documentée) + DemoFintechActivity (écran KwikPay simulé, parcours imposé).
- **Mode démo OFFLINE** : P1→P5 jouables sans serveur ni internet via la bulle
  (un tap = annule le tour courant et joue le suivant). Mode serveur prêt pour M2.
- Pièges déjà corrigés dedans : unités safeBottom (dp vs px), margins sur ancres,
  champ self-exclusion (l'écran démo doit être lisible), active l'accessibilité
  via adb = nom de composant COMPLET obligatoire sur XOS.

Le membre 1 (LEARN.md) reconstruit son propre moteur pédagogique dans `moteur-rendu/` ;
`moteur-rendu-ia/` est la **référence production** prête pour le 14 (et la base de
l'intégration avec M2/M3). Fusion sur `dev` à la validation de l'équipe.

## 10. Prochaines actions (dans l'ordre)

**Membre 1 (utilisateur) — cette semaine :**
- [ ] Leçons 1→3 de LEARN.md (app Android, filtre sécurité, ScreenContext)
- [ ] Créer `fixtures/actions-p1-solde.json` (2 min depuis le contrat §5) pour sa Leçon 6
- [ ] Poser la protection de `master` sur GitHub web (docs/03 §4)
- [ ] Question aux organisateurs : environnement de test Android ou web ? format de dépôt ?
      (via le représentant d'équipe — réponse influe sur M1/M4)

**Membre 2 (dès identification) :**
- [ ] Activer AWS (vérifier crédits) + alarmes facturation
- [ ] Gateway WS + harnais validateur + Bedrock prompt v1 (test sur fixtures)
- [ ] KB : `kb/demo-fintech/` (ui_inventory, lexique v1, phrases.json v0)

**Membre 3 (dès identification) :**
- [ ] Fine-tune STT (EC2 spot ou Kaggle) sur Common Voice ewo
- [ ] Scripter les 60 phrases ewondo (avec le relecteur dès recruté)
- [ ] fixtures/stt-test-30.ewo (30 phrases enregistrées → mesure WER)

**Équipe :**
- [ ] Valider le cadrage + le contrat ensemble (docs/01 et 02)
- [ ] Intégration complète P1-P5 en français le 11 nov. · ewondo le 11-12 · vidéo le 12-13
- [ ] Gel le 13 soir : dev → master, tag `preselection`

## 11. Conventions de session ZCode

- Le membre 1 parle français ; réponses en français.
- Brainstorm cadrage = back-and-forth (poser des questions plutôt que supposer).
- Ne jamais écrire le code des LEARN.md à sa place (mentorat, pas génération) ;
  revues via adb acceptées et attendues.
- Tout changement de payload passe par une révision versionnée de docs/02 — jamais à l'oral.
- Chaque affirmation visuelle « validée » doit être prouvée par capture adb de la
  COMPOSITION complète (leçon apprise le 8 nov.).
