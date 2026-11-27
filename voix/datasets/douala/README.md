# Dataset linguistique & vocal Duálá — NkapMobile × SAFINUM 2026

Ce dossier archive le corpus humain natif Duálá collecté pour NkapMobile :

- **`dataset-douala.json`** et **`dataset-douala.csv`** : export du collecteur (`65 / 71` textes UI remplis, `45` enregistrements vocaux natifs `.webm`).
- **`audios/`** : **45 enregistrements vocaux natifs** (`S05_site_05.webm` → `S71_site_71.webm`) prononcés par un locuteur natif Duálá.

## Hiérarchie de priorité appliquée dans le projet
1. **Lexique manuscrit PDF** (`docs/lexique-douala-pdf.json`) — source prioritaire en cas de conflit (`Idiba bwam`, `Mususedi`, `Miango`, `Sumua`, `Wa la ne`, `Epasi`, `Kotele`, `Musongi`…).
2. **Complément SAFINUM `.docx`** (`cerveau/app/sandbox/translations/dua.json`) — couverture des 89 clés officielles du bac à sable.
3. **Export collecteur ZIP (`nkap-douala-20261127-1815.zip`)** — utilisé pour :
   - les **45 audios natifs `.webm`** (exposés dans `cerveau/static/audio/dua/` et `nkap-extension/voice-bank/dua/`),
   - le comblement des dernières clés UI (`Compte courant`, `Type d'opération`, `Compte Safinum`, `Autre banque`, `Solde après opération`, `Opération`, `Message important`, etc.).
