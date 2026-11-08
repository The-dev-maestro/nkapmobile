# nkapmobile — Workflow Git de l'équipe
### v1 · Un seul repo : `deiryl237/nkapmobile`

## 1. Les branches

| Branche | Rôle | Qui écrit |
|---|---|---|
| `master` | **livrables** : l'état envoyé au jury (14 nov.), toujours fonctionnel | personne directement — uniquement merge depuis `dev` |
| `dev` | **intégration** : la fusion des 3 modules, doit toujours compiler | tout le monde (via merges de branches perso) |
| `perso/deiryl-moteur-rendu` | bac à sable du membre 1 (moteur de rendu + contexte) | membre 1 seul |
| `perso/<pseudo>-cerveau` | bac à sable du membre 2 | membre 2 seul |
| `perso/<pseudo>-voix` | bac à sable du membre 3 | membre 3 seul |

## 2. La règle du jeu

1. **On ne pousse jamais sur `master` directement.** `master` = `dev` quand dev est
   stable (au moins après chaque grosse étape : le 11, le 13, le 14).
2. **`dev` doit toujours compiler.** On merge sa branche perso dans `dev` quand
   son module ajoute quelque chose d'utilisable — pas un WIP qui casse les autres.
3. **Chacun vit dans sa zone de dossiers** (contrat §10) :
   - membre 1 → `moteur-rendu/`
   - membre 2 → `cerveau/` + `fixtures/`
   - membre 3 → `voix/` + lexique
   - `docs/` → commun (tout le monde peut améliorer, merge sur `dev`)
4. **Un commit = une idée.** Message court et explicite (français OK) :
   `moteur-rendu: cercle manuscrit sur nœuds réels`, `voix: script des 60 phrases`.
5. **En cas de doute, on en parle avant de merger sur dev.**

## 3. Commandes — cheat-sheet par membre

### setup (une fois, au premier jour)
```bash
git clone https://github.com/deiryl237/nkapmobile.git
cd nkapmobile
git checkout dev                          # base d'intégration
git checkout -b perso/<pseudo>-<module>   # TA branche perso
git push -u origin perso/<pseudo>-<module>
```

### au début de chaque session
```bash
git checkout dev && git pull              # récupérer l'intégration à jour
git checkout perso/<pseudo>-<module>
git merge dev                             # ta branche repart de la dernière intégration
```

### quand tu as fini un morceau utilisable
```bash
git add <tes dossiers> && git commit -m "<message>"
git push
# puis fusionner dans dev :
git checkout dev && git pull
git merge perso/<pseudo>-<module>
git push
git checkout perso/<pseudo>-<module>      # retourner dans ton bac à sable
```

### en cas de conflit de merge
```bash
# git te montre les fichiers en conflit — ouvre-les, cherche <<<<<<<
# garde la bonne version, supprime les marqueurs, puis :
git add <fichier>
git commit                                # conclut le merge
```

## 4. Protection de `master` (à faire sur GitHub, 2 min)

Sur github.com → `deiryl237/nkapmobile` → **Settings → Branches → Add branch
protection rule** :
- Branch name pattern : `master`
- ☑ Require a pull request before merging (ou, en équipe de confiance : laisser
  libre mais SE MERGER depuis dev — la règle n°1 tient par discipline)
- ☑ Do not allow force pushes · ☑ Do not allow deletions

> ⚠️ Repos privé recommandé tant que la compétition n'est pas terminée.

## 5. Convention de commits

`<zone>: <ce qui a changé>` — zones : `moteur-rendu`, `cerveau`, `voix`,
`fixtures`, `docs`, `kb`.
Exemples :
- `moteur-rendu: AccessibilityService filtre les champs de saisie`
- `voix: 60 phrases ewondo écrites, 22 enregistrées`
- `docs: note technique v1`

## 6. Repères du 14

| Date | Événement Git |
|---|---|
| 11 nov. | intégration complète P1-P5 sur `dev` (premier test team) |
| 12-13 nov. | vidéo + note technique gelées sur `dev` |
| 13 nov. soir | `dev` → `master` : l'état officiel du livrable |
| 14 nov. | dépôt depuis `master` (tag `preselection`) |
