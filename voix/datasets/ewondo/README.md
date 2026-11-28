# Dataset linguistique Ewondo — NkapMobile × SAFINUM 2026

Ce dossier archive le corpus humain natif Ewondo validé par **Nsia** pour NkapMobile :

- **`dataset-ewondo.json`** et **`dataset-ewondo.csv`** : export du collecteur (`nkap-ewondo-20261128-0116 (1).zip`, exporté le `2026-11-28T00:16:55Z`).
- **Couverture** : `55 / 157` textes remplis (`A01`–`A55` hors `A15`/`A30`, plus `B03` `ussd.balance` et `C17` `WITHDRAWAL`), `0` audio enregistré pour le moment.

## Intégration appliquée dans le projet
1. **`cerveau/app/sandbox/translations/ewo.json`** : mise à jour prioritaire des 52 clés UI remplies par Nsia (en préservant les placeholders `{name}`, `{max}`, `{operator}`, `{amount}` requis par `translate_ui`).
2. **`cerveau/m5_kb/safinum-sandbox/playbook.json`** : ajout des nouveaux libellés Ewondo dans `ui_translations`, `action_buttons`, `screen_detectors`, `screen_guides` et `qa_shortcuts` (rétrocompatible avec les anciens libellés).
3. **`cerveau/app/core/m2_service.py` & `cerveau/app/sandbox/language.py`** : ajout des gloses Ewondo → Français, des mots-clés d'intention (`ikola`, `dimi`, `ndouang`, `yi wa yebeu`, `tsenegue`, `vaagui`…) et du gabarit USSD solde (`B03`).
4. **`nkap-extension/src/lexicon.js`** : alignement des libellés Ewondo validés pour la traduction DOM.
