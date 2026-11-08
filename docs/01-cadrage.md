# nkapmobile — Dossier de cadrage v1
### SAFINUM Innovate Challenge · Présélection du 14 novembre 2026

> **nkap** *(nom)* — l'argent en camfranglais, compris dans tout le Cameroun.
> nkapmobile : la couche qui rend n'importe quelle app financière compréhensible
> en langue nationale — par la voix, le dessin et l'ewondo.

**Statut** : v1 à réviser en équipe · **Rédaction** : 7 nov. 2026 · **Échéance prototype** : 14 nov. 2026

---

## 1. Contexte et opportunité

- 21,6 M de comptes mobile money au Cameroun, **zéro interface en langue nationale**.
- La personne de référence : Yolande, 58 ans, marché Mokolo — ne lit pas couramment
  le français, n'ose pas utiliser l'app de sa banque, dépend d'un tiers pour chaque
  transaction.
- Le défi officiel (PDF présélection) : rendre un service financier numérique
  accessible dans **au moins une langue nationale**, **sans modifier son code source**,
  avec parcours imposé (solde, frais, transfert, récapitulatif, erreur/sécurité) et
  **contenu inédit injecté pendant la démo**.

**Notre thèse** : la meilleure traduction pour quelqu'un qui ne lit pas, c'est de
**voir et d'entendre** — un assistant qui annote l'écran réel (cercle, écriture,
soulignement, cadre) pendant qu'une voix ewondo raconte, pilotés en temps réel
par un LLM qui voit l'écran.

## 2. Exigences officielles mappées (source : PDF de l'épreuve)

| Exigence du sujet | Notre réponse nkapmobile |
|---|---|
| Prototype fonctionnel sur interface existante **ou simulée** | Notre app fintech simulée + **environnement de test du comité** dès qu'il est publié |
| **Sans modification du code source** du service cible | **AccessibilityService Android** : lecture de l'arbre d'UI + overlay par-dessus toute app — zéro intégration |
| 5 capacités minimales (adaptation linguistique, parcours, préservation des infos, indépendance, contenu inédit) | Voir matrice critères §5 |
| Vidéo 3 min max | Scénario Yolande complet, tourné le 12-13 nov. |
| Note technique (architecture, intégration, dépendances, **limites connues**) | Extraite de la §4 de ce dossier, formatée le 12 nov. |
| **Méthode de validation linguistique** | Locuteur externe (relecture à distance) du lexique + des phrases vocales ; documentée dans la note |
| Déclaration des composants tiers | Tableau licences §4.5 (CC0 / CC-BY / NC / OFL) |
| Simulations uniquement, aucune donnée réelle | App simulée ; lecture de l'écran limitée aux textes affichés, **jamais les champs de saisie** (PIN exclu par design) |

## 3. Objectifs

| # | Objectif | Mesurable |
|---|---|---|
| O1 | Se qualifier pour la finale (top du classement présélection) | Score ≥ seuil sur les 100 pts |
| O2 | Pipeline ewondo complet bout-en-bout le 14 nov. | Question parlée ewondo → réponse vocale ewondo + dessin, sur parcours imposé |
| O3 | « Contenu inédit » maîtrisé | Message nouveau injecté à la volée → scène générée correcte (généré par le LLM, pas scripté) |
| O4 | Base produit réutilisable | Modules à interfaces propres, core partagé KMP, déployable par entreprise (RAG) |

**Hors périmètre du 14** : autres langues (architecture prête, démo non), port iOS
(architecture prête, code non), fine-tuning entreprise (RAG suffit), app web/extension.

## 4. Architecture cible

### 4.1 Vue d'ensemble — 5 modules, 5 interfaces

```
        ┌────────────────────────── sur l'appareil (Android) ──────────────────────┐
        │                                                                          │
        │  ┌────────────────────────────┐        ┌──────────────────────────────┐   │
        │  │ M1. MOTEUR DE RENDU (SDK)  │        │ M4. FOURNISSEUR DE CONTEXTE  │   │
        │  │ core KMP (pur Kotlin)      │        │ AccessibilityService         │   │
        │  │ + couche Android (Canvas)  │        │ arbre UI réel → JSON contexte │  │
        │  └──────────┬─────────────────┘        └──────────────┬───────────────┘   │
        │             │ I4. execute(action)                     │ I5. screenContext │
        │             │                                         ▼                   │
        └─────────────┼─────────────────────────────────────────────────────────────┘
                      │ WebSocket (flux d'actions)
                      ▼
        ┌─────────────────────────── cloud (AWS, crédits équipe) ──────────────────┐
        │  passerelle WS ──► M2. CERVEAU (harnais LLM sur Bedrock)                  │
        │                      │ I3. answer(question, contexte, KB) → FLUX          │
        │                      │     d'actions typées (speak + gestes entrelacés)   │
        │                      ▼                                                   │
        │  M3. VOIX ── I1. transcribe(audio) → {texte, langue}                      │
        │          ── I2. speak(texte) → audio (banque ewondo + mms-tts-ewo)        │
        │  M5. KB ENTREPRISE ── index RAG (inventaire UI, FAQ, lexique, tarifs)     │
        └───────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Le protocole central : flux d'actions (décision actée)

Le cerveau ne renvoie pas « une réponse + un script » : il streame **un seul flux**
d'actions typées où `speak` et les gestes s'entrelacent — le dessin suit la parole
parce qu'ils sortent du même flux. Le vocabulaire des gestes (validé au PoC) :
`circle` · `write` · `underline` · `frame` · `arrow` · `caption` (+ `clear`/`hide`).

- v1 (14 nov.) : le flux arrive par blocs (une phrase + ses gestes par message WS).
- v2 (finale) : streaming token par token — **l'interface ne change pas**.
- Les règles de composition (≤ 3 marques simultanées, contraste selon tone,
  zones sûres, montants jamais reformulés) vivent dans le **harnais**, pas dans
  le LLM : chaque action est validée avant exécution, action invalide = rejet.

### 4.3 Modules et responsabilités

| Module | Resp. | Contenu technique |
|---|---|---|
| **M1 Moteur de rendu** | **[membre 1 — toi]** | `core/` KMP : protocole, types DSL, géométrie manuscrite (tracé progressif, tremblé), règles de composition. `android/` : overlay Canvas par-dessus toute app, ancrage sur bornes des nœuds d'accessibilité, bulle assistant, sous-titres Andika |
| **M2 Cerveau + harnais** | [membre 2 ?] | WS passerelle, prompt système (règles + lexique), Bedrock Claude, RAG sur KB, validation du flux d'actions, templates de phrases verrouillées (banque vocale d'abord, TTS libre en repli) |
| **M3 Voix** | [membre 3 ?] | STT : Whisper fine-tuné Common Voice ewo (14,4 h CC0) sur EC2 GPU ; TTS : banque ~60 phrases enregistrées + `mms-tts-ewo` en repli libre ; pipeline audio (compression, VAD) |
| **M4 Fournisseur de contexte** | avec M1 | AccessibilityService : arbre → contexte compact (id, texte, bornes, tone estimé) ; filtrage sécurité (champs de saisie exclus) |
| **M5 KB entreprise** | avec M2 | Dossiers par entreprise déployée : inventaire d'écran, FAQ, lexique financier FR↔ewondo, tarifs — injecté au cerveau par RAG (le fine-tuning = roadmap post-hackathon) |

### 4.4 Sécurité & préservation financière (20 pts du jury)

- **Les montants, frais, bénéficiaires ne sont jamais traduits ni reformulés** :
  chiffres et noms passent tels quels ; le harnais rejette toute action qui les altère.
- Lexique financier verrouillé (un seul terme ewondo par concept financier).
- Lecture d'écran : textes affichés uniquement — les champs de saisie (PIN) sont
  exclus par le M4 et jamais envoyés au cloud.
- Mode dégradé assumé : hors ligne → sous-titres + dessin sans voix.

### 4.5 Dépendances & licences (à déclarer au jury)

| Composant | Usage | Licence |
|---|---|---|
| Common Voice v27 ewo (14,4 h) | fine-tune STT | CC0 |
| cameroon_bibles (flagship-ai) | corpus FR↔ewondo (RAG/éval) | CC-BY-4.0 |
| mms-tts-ewo | TTS libre (repli) | CC-BY-NC (démo) |
| Andika (SIL) | typographie | OFL |
| Whisper (OpenAI) | base STT | MIT |
| Bedrock Claude | cerveau | service AWS (payant) |
| dictionnaires ewondo (1956/2001) | sources lexique | citation académique |

## 5. Matrice critères du jury (100 pts) → nos réponses

| Critère | Pts | Réponse |
|---|---|---|
| Fonctionnement du prototype | 25 | Parcours imposé complet en ewondo, bout-en-bout, démo reproductible + vidéo |
| Intégration & indépendance | 20 | AccessibilityService : zéro modification, toute app Android ; preuve sur 2 apps différentes |
| Sécurité & préservation infos | 20 | §4.4 : montants intouchés, PIN exclu, rejet harnais |
| Accessibilité & UX | 15 | Voix + dessin + sous-titres : conçu pour non-lecteurs ; langage « le tableau » validé au PoC |
| Adaptation contenu inédit | 10 | Le LLM génère la scène dynamiquement (pas de scènes pré-écrites) — c'est le cœur du design |
| Faisabilité & documentation | 10 | Note technique depuis ce dossier ; architecture modulaire documentée |

**Facteur éliminatoire** : erreurs linguistiques modifiant le sens → validation
humaine obligatoire de TOUTE phrase vocale ewondo avant le 14.

## 6. Équipe & répartition

| Membre | Module | Notes |
|---|---|---|
| Membre 1 (toi) | **M1 + M4** (moteur de rendu, contexte, vision artistique) | possède la vision « le tableau », appareils de test |
| Membre 2 | M2 + M5 (cerveau, harnais, RAG, AWS) — **à confirmer** | |
| Membre 3 | M3 (voix, fine-tune STT, banque vocale) + recrutement locuteur — **à confirmer** | |

Transverses : la **note technique** (membre 2), la **vidéo** (membre 1 réal.,
membre 3 voix), le **lexique** (membre 3 + locuteur externe).

## 7. Plan J-7 (7 → 14 nov.)

| Jour | M1 rendu+contexte | M2 cerveau | M3 voix | Jalon équipe |
|---|---|---|---|---|
| **7 (auj.)** | validation du cadrage en équipe ; repo Git + projets vides ; compte AWS activé | idem | idem + **lancement recrutement locuteur** (NABU/IHS, Univ. Yaoundé I, ANACLAC/CABTAL, paroisses) | cadrage v2 acté |
| **8** | squelette KMP + AccessibilityService qui affiche l'arbre en log | passerelle WS + Bedrock + prompt v1 | fine-tune STT lancé sur EC2 spot | questions aux organisateurs envoyées (env. de test : app Android ou web ? format de dépôt ?) |
| **9** | overlay Canvas : cercle/underline fluide sur app tierce (Chrome) | harnais : validation d'actions + templates | test du checkpoint STT (WER sur phrases type) | premier flux bout-en-bout **en français** |
| **10** | write/arrow/frame + sous-titres + ancrage sur nœuds réels | RAG KB v1 (notre app simulée) + lexique branché | banque vocale : script des 60 phrases envoyé au locuteur | démo ewondo textuelle (sans voix) |
| **11** | app fintech simulée intégrée au parcours imposé ; polish tracé | contenu inédit : injection de messages tests | enregistrements reçus → montage + intégration | répétition 1 bout-en-bout ewondo |
| **12** | remplissage des derniers gaps démo | note technique rédigée | TTS libre en repli testé | **répétition 2 + tournage vidéo** |
| **13** | buffer | buffer | buffer | vidéo montée 3 min, tout gelé |
| **14** | — dépôt — | | | description + prototype + vidéo + note technique + validation linguistique |

## 8. Risques & replis

| Risque | Prob. | Repli |
|---|---|---|
| Env. de test du comité = web (pas Android) | moy. | extension navigateur sur le même protocole (question posée aux organisateurs le 8) ; démo Android sur notre app simulée en parallèle |
| Pas de locuteur à J-3 | moy. | voix TTS libre seule + validation linguistique reportée à la finale ; le lexique est validé par le corpus biblique en attendant |
| Fine-tune STT faible (WER > 40 %) | moy. | questions écrites/clics ; STT français pour la démo « technique » + ewondo sur phrases de la banque |
| Latence bout-en-bout > 3 s | moy. | pré-génération pendant la parole (streaming STT), actions prioritaires d'abord |
| Crédits AWS insuffisants | faible | tout tourne aussi en local (laptop) — le cloud n'est pas un chemin critique |
| Erreur linguistique le jour J | — | **aucune phrase non validée ne sort** : règle absolue du harnais |

## 9. Annexe — Budget AWS (crédits équipe)

Règles d'or : **aucune instance allumée sans usage** (le GPU oublié = 254 $/mois),
**alarmes de facturation à 60 $ et 80 $**, vérifier à l'activation que les crédits
couvrent Bedrock + EC2 et leur date d'expiration.

| Poste | Service | Estimation |
|---|---|---|
| Fine-tune STT ewondo | EC2 GPU spot, 4-8 h (ou Kaggle gratuit) | 3-6 $ (0 $ si Kaggle) |
| Inférence dev (CPU int8, laptops en local) | c6i/t3 spot | 10-20 $ |
| Inférence démos + finale (GPU) | EC2 on-demand, heures comptées | 5-10 $ |
| Cerveau (Bedrock Claude) | Haiku en dev, Sonnet optionnel finale | 10-25 $ |
| Passerelle WS + S3/CloudFront | API Gateway/ALB + assets | 10-20 $ |
| **Total** | | **~40-80 $** |

100 crédits suffisent avec les règles ci-dessus ; 300 = marge totale.
Le cloud n'est jamais un chemin critique : tout le pipeline tourne aussi en local
sur laptop (repli §8).

## 10. Vision post-hackathon (pour le jury, 10 lignes)

nkapmobile devient la **couche d'accessibilité linguistique** des fintechs
d'Afrique centrale : un SDK + un service cloud qui s'adapte à toute app Android
existante, déployé par entreprise via son dossier KB (RAG), extensible de
l'ewondo aux ~60 langues camerounaises déjà corpus-alignées (flagship-ai/lingo.cm).
Modèle : licence SDK + abonnement cloud par institution financière. Le port iOS
(sdk in-app) et le fine-tuning par entreprise sont la roadmap naturelle.
