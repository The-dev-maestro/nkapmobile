# Guide M5 — Connaissance applicative & Scénarios débutants (SAFINUM · Wave · Max it)

> Ce document décrit la couche de connaissance applicative **M5 KB** (`cerveau/m5_kb/<app>/playbook.json`) qui permet au harnais NkapMobile de guider un utilisateur peu familier des services financiers numériques avec **zéro hallucination**, même sur un modèle local léger (1,5B).

---

## 1. Principe architectural (Harnais + Playbook M5)

Un petit LLM local (`qwen2.5:1.5b`) excelle pour reformuler et comprendre une intention, mais il ne connaît pas les pièges propres à chaque application (ex. un texte d'aide *« Jusqu'à 500 000 FCFA par opération »* confondu avec un montant à envoyer, ou un solde sans libellé au sommet de Wave).

Chaque application prise en charge dispose donc d'une fiche déclarative `cerveau/m5_kb/<app>/playbook.json` chargée par `AppPlaybookStore` (`cerveau/app/core/app_kb.py`) :
- **`match_packages` / `match_urls` / `match_text_cues`** : identification automatique de l'application active.
- **`ui_translations` & `action_buttons`** : normalisation FR/EN/Ewondo/Duálá et détection des icônes cliquables (même quand le `TextView` enfant renvoie `clickable=false`).
- **`screen_guides`** : réponse guidée immédiate quand l'utilisateur demande *« Je dois faire quoi ici ? »*, *« Explique-moi cet écran »*, *« Je suis perdu »*.
- **`qa_shortcuts`** : réponses ciblées aux questions fréquentes d'un débutant sur cette application (QR code, Coffre/Vault, contacts enregistrés, plafond, annulation, masquage de solde…).

---

## 2. Environnement de test SAFINUM (`banque-demo.sandbox` — Web & Mobile)

Fiche : `cerveau/m5_kb/safinum-sandbox/playbook.json`

| Écran | Contenu réel | Questions débutant typiques | Comportement Nkap |
|---|---|---|---|
| **Accueil (`/home`)** | Solde disponible (`Itan ineu` / `Moni ma pene`), 4 raccourcis (`Lomo moni`, `Yaan mfie ai kalara`, `Kus kredi telefon`, `Itang mvet yam`), dernières opérations, bouton `Wog`/`Senga` | *« Quel est mon solde ? »*<br>*« Comment envoyer de l'argent ? »*<br>*« Je dois faire quoi ici ? »*<br>*« À quoi sert le bouton Wog ? »* | Cercle doré seul sur le solde (sans tableau redondant) ; cadre `Appuie ici` sur `Lomo moni` ; guide complet sur *« Je dois faire quoi ici ? »*. |
| **Transfert (`/transfer`)** | Champs `Bénéficiaire` (`Mod a non moni`) et `Montant` (`Itan`), indice **`Jusqu'à 500 000 FCFA par opération`** (`Akui 500 000 FCFA a mvet wuo`), liste **`Mes bénéficiaires`** (`Blaise Tchami`, `Brenda Nana`, `Carine Njoya`, `Ibrahim Essomba`), boutons `Annuler` (`Vaa`) & `Continuer` (`Kele obusu`) | *« Je dois faire quoi ici ? »*<br>*« Je dois envoyer 500 000 FCFA ? »*<br>*« C'est quoi la liste à droite ? »*<br>*« Comment annuler ? »* | **① Bénéficiaire → ② Montant → cadre ③ Continuer**. L'indice `500 000 FCFA` est marqué `role=hint` (jamais confondu avec un montant saisi) et les contacts enregistrés sont expliqués comme raccourcis cliquables. |
| **Payer (`/pay`)** | Onglets `Facture` (`Kalara`) / `Crédit` (`Kredi`), fournisseur (`ENEO`, `CAMWATER`, `CANAL`, `CAMTEL`), numéro, montant, `Continuer` | *« Je dois faire quoi ici ? »*<br>*« Comment payer ENEO ? »* | Guide pas-à-pas + cadre sur `Continuer`. |
| **Récapitulatif (`/review`)** | Bénéficiaire, Montant, Frais (`Mbug`), Total à débiter (`Ntolan wog`), Solde après opération (`Itan e li'i`), boutons `Confirmer` (`Yemban`), `Modifier` (`Tyende`), `Annuler` | *« Combien il me restera après ? »*<br>*« Je dois faire quoi ici ? »*<br>*« Je veux corriger le montant »* | Ardoise `flow` tracée en direct (`Montant → Frais → Solde après`) ; cadre sur `Confirmer` ; rature rouge `strike` en cas de correction. |
| **Reçu (`/receipt`)** | `Opération réussie`, référence (`Nombo ndem`), nouveau solde (`Itan mfefe`) | *« L'argent est bien parti ? »* | Confirmation claire + mise en valeur du nouveau solde et de la référence. |
| **Historique (`/history`)** | Filtres `Tout` / `Reçus` / `Envoyés`, statuts (`Confirmé`, `En attente`, `Annulé`, `Échoué`) | *« Quelles sont mes dernières opérations ? »* | Liste/barres tracées progressivement + coches vertes / croix rouges selon le statut. |

---

## 3. Wave Mobile Money (`com.wave.personal` — Sponsor officiel)

Fiche : `cerveau/m5_kb/wave/playbook.json` (calibrée sur dump `uiautomator` réel de Wave Android)

Particularités techniques de l'arbre d'accessibilité Wave observées sur appareil réel :
1. Dans le XML Android, la **liste de transactions** (`y=834`, ex. `GIMAC transfer ... | 1.500F`) apparaît **avant** le bandeau supérieur fixe (`1.500F` centré en `y=157, h=72px`, accompagné de `content-desc="Hide balance"` en `y=186`). Le cerveau trie donc les nœuds en ordre visuel `(y, x)` et identifie prioritairement le grand montant en tête d'écran / adjacent à `Hide balance` comme **`Solde disponible`**.
2. Les 4 icônes principales (`Send`, `Bills`, `Vault`, `More`) ont `clickable=false` sur leur `TextView` enfant (le conteneur parent porte le clic). Le playbook les classe explicitement en `role=button`.

Scénarios débutants couverts sur Wave :
- *« Quel est mon solde ? »* → Cercle doré uniquement sur le **`1.500F` du haut** (jamais sur la transaction du bas), 1 phrase vocale + sous-titre court.
- *« Comment envoyer de l'argent ? »* → Cadre `Appuie ici` directement sur **`Send`** (jamais `Hors contexte`).
- *« Comment payer une facture ? »* → Cadre `Appuie ici` sur **`Bills`**.
- *« C'est quoi Vault / le coffre ? »* → Cadre sur **`Vault`** + explication simple de l'épargne Wave.
- *« À quoi sert le QR code ? »* → Explication claire dépôt/retrait/paiement marchand sans dicter son numéro.
- *« Comment cacher mon solde ? »* → Cercle sur l'icône œil **`Hide balance`**.
- *« Je dois faire quoi ici ? »* → Tour d'horizon complet de l'écran d'accueil Wave.

---

## 4. Orange Max it (`com.orange` / `maxit`)

Fiche : `cerveau/m5_kb/maxit/playbook.json` (calibrée sur captures réelles sur TECNO KN4)

Particularités gérées :
- Fusion automatique dans `ScreenReaderService.kt` des `TextView` séparés `Nombre + Devise` (`"24 828,58"` + `"FCFA"` → `"24 828,58 FCFA"` ; `"1,04"` + `"U"` → `"1,04 U"`).
- Mapping anglais → français (`Main Account` → `Solde disponible`, `Money transfer` → `Envoyer de l'argent`, `Cancel transaction` → `Annuler une transaction`, `Buy a bundle` → `Acheter un forfait`, `Top Up` → `Recharger du crédit`, `My Credits` → `Mon crédit d'appel`).

---

## 5. Ajouter une nouvelle banque / fintech en 5 minutes

Créez simplement `cerveau/m5_kb/<nom-banque>/playbook.json` en suivant le schéma de `wave/playbook.json` et redémarrez `nkap-cerveau` : le chargeur `AppPlaybookStore` détecte et active la nouvelle application automatiquement, sans modifier une seule ligne de code Python ou Kotlin.
