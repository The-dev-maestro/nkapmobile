# LEARN.md — Parcours d'apprentissage nkapmobile
### Ton module : M1 (moteur de rendu) + M4 (contexte d'écran) · Kotlin/Android, zéro prérequis

> **Ton profil** : .NET / MAUI → tu as déjà les concepts (XAML, async/await, classes,
> propriétés). Kotlin t'est nouveau, pas la programmation. Ce parcours traduit ce que
> tu sais vers ce qu'il faut, et chaque leçon construit un morceau RÉEL de nkapmobile.
>
> **La règle du jeu** (toolkit Manware, activé dans ce repo) : tu essaies d'abord,
> tu prédis, l'IA donne des indices par palier. L'IA (Antigravity **ou** ZCode)
> ne t'écrit jamais la solution tant que tu ne la demandes pas explicitement.
>
> **Échéance** : prototype complet le 14 nov. Chaque leçon produit un livrable réel.

---

## 0. Installation (30 min, aujourd'hui)

1. Ouvre le dossier `nkapmobile/` dans **Antigravity**
2. Panel Customizations → active `.agents/rules/learning-companion.md` en **Always On**
3. Familiarise-toi avec les workflows : `@learn` (démarrer), `@hint` (bloqué),
   `@debug` (bug), `@autopsy` (après avoir corrigé), `@code-review`
4. Référence du vocabulaire visuel : `docs/02-architecture-interfaces.md` §5
   (les 9 actions) — c'est TA bible produit
5. Le spike de faisabilité est archivé hors repo
   (`Desktop/projets/architecture logicielle/archive-spike-context-overlay/`) :
   **référence de lecture uniquement** — il prouve que tout ce que tu vas coder
   fonctionne, mais tu écris le tien

**Qui fait quoi** :
- **Antigravity + toolkit** = ton compagnon d'apprentissage quotidien (ne code pas)
- **ZCode (session séparée)** = architecte & testeur : relecture via adb sur ton
  téléphone, réponses architecture, débogage intégration, tests du contrat
- **Toi** = tu tapes chaque ligne

---

## Traduction express C# → Kotlin (à garder sous les yeux)

| C# | Kotlin | Note |
|---|---|---|
| `var x = 5;` / `readonly` | `var x = 5` / `val x = 5` | `val` = immuable par défaut |
| `record Foo(int A)` | `data class Foo(val a: Int)` | égalité/copie auto |
| `string?` (nullable ref) | `String?` | null-safety **obligatoire** : `?.` et `?:` |
| `x?.Method() ?? y` | `x?.method() ?: y` | opérateur Elvis `?:` |
| `switch` / pattern matching | `when` | plus puissant : `when(x) { is A -> … }` |
| `async/await` | `suspend fun` + coroutines | v2 — pas besoin avant la semaine 2 |
| `IEnumerable<T>.Select/Where` | `.map {} .filter {}` | idem |
| `using` (dispose) | `.use { }` | idem |
| XAML | Compose `@Composable` **ou** XML layouts | le spike = View/XML + Canvas |
| `partial class`/héritage | classes + interfaces `:` | pareil |

---

## Leçons 1 — « Hello Android » (le shell, pas le contenu)
**Objectif produit** : un projet Android `app/` qui affiche « nkapmobile » sur ton Infinix.
**Nouveaux concepts** : structure Gradle, Manifest, Activity, installation adb.
**Comment** : crée le projet toi-même (Antigravity tient ta main via `@hint`).
Les fichiers Gradle du spike archivé (`archive-spike-context-overlay/*.gradle.kts`,
dans `Desktop/projets/architecture logicielle/`) sont ta référence de
configuration — compare, comprends, adapte. Installe via `adb install`.
**Validation** : capture d'écran du téléphone montrant ton app.

## Leçon 2 — Kotlin par la pratique (ton filtre de sécurité)
**Objectif produit** : la fonction `isSensitiveNode(className, isPassword)` — décide
si un nœud d'UI doit être exclu du contexte (règle PIN du contrat §2).
**Nouveaux concepts** : fonctions, `when`, null-safety, `Boolean` logic.
**Test** : écris 6 cas de test en Kotlin (fichier `main` exécutable) — `"EditText"` →
true, `isPassword=true` → true, `TextView` → false…
**Validation** : ZCode relit et tente de casser ta fonction avec des cas tordus.

## Leçon 3 — L'arbre d'accessibilité (le cœur de M4)
**Objectif produit** : parcourir l'arbre d'une app tierce et produire le JSON
ScreenContext (contrat §2) — affiché en logcat, tag `nkapspike`.
**Nouveaux concepts** : AccessibilityService, `AccessibilityNodeInfo`, récursivité,
`JSONObject`, recycle() des nœuds.
**Comment** : lis le service du spike archivé (`SpikeAccessibilityService.kt`)
pour comprendre, puis
réécris ta propre version dans `app/` SANS le copier — en commençant par la
récursion sur 5 nœuds, puis les bounds, puis le JSON.
**Validation** : ton JSON logcat couvre Chrome + Paramètres, PIN exclu.

## Leçon 4 — Canvas : ton premier trait manuscrit
**Objectif produit** : dessiner un **soulignement jaune tremblé** sous n'importe quel
texte à l'écran (le geste `underline` du contrat).
**Nouveaux concepts** : View custom, `onDraw`, `Paint` (stroke, round cap), arcs et
courbes quadratiques, `postInvalidateOnAnimation` (boucle de rendu).
**Comment** : le soulignement = une ligne avec légère courbure sinusoïdale + jitter
aléatoire. Compare avec `handUnderline()` du spike archivé APRÈS avoir écrit le tien.
**Validation** : capture adb du soulignement sous le titre des Paramètres Android.

## Leçon 5 — L'overlay (être au-dessus de tout)
**Objectif produit** : ton sous-solignement se dessine au-dessus de n'importe quelle
app, sans permission.
**Nouveaux concepts** : WindowManager, `TYPE_ACCESSIBILITY_OVERLAY`, flags
`NOT_TOUCHABLE`, `PixelFormat.TRANSLUCENT`.
**Validation** : le soulignement apparaît dans Chrome ET dans une app bancaire
réelle de ton choix, sans modifier leur code.

## Leçon 6 — Le protocole : ton moteur exécute le contrat
**Objectif produit** : parser un flux d'actions JSON (contrat §5) et exécuter
`underline` + `write` + `frame` sur l'écran réel.
**Nouveaux concepts** : `data class` + `sealed class` (≡ records C#),
`JSONObject`/parsing, dispatch par `when`, état des marques vivantes (≤ 3).
**Comment** : démarre de `fixtures/actions-*.json` (M2 les fournira — sinon crée
2 exemples toi-même depuis le contrat).
**Validation** : rejouer un flux fixture sur l'app démo → la séquence visuelle
correspond au concept « le tableau ».

## Leçon 7 — Intégration (le 11-12 nov.)
**Objectif produit** : ScreenContext (leçon 3) + renderer (leçon 6) branchés sur le
serveur de M2 via WS, parcours P1 complet en ewondo.
**Nouveaux concepts** : WebSocket (OkHttp), cycles de vie, gestion d'erreur offline.
**Validation** : la démo officielle tourne sur TON téléphone.

---

## Journal d'apprentissage (dossier `learning/`, du toolkit)

- `concepts.md` — un concept appris = une entrée (ta propre formulation !)
- `mistakes.md` — chaque bug corrigé : qu'as-tu cru ? qu'a fait le code réellement ?
- `questions.md` — ce que tu n'as pas compris (ZCode y répond en revue)
- `review.md` — les revues de ZCode : ce qui était bien, ce qui était fragile

## Les 3 règles d'or

1. **Tu tapes tout.** Copier le spike = apprendre à copier, pas à coder.
2. **Prédis avant de tester.** « Ce code va faire X » — puis vérifie. Si faux,
   c'est là que tu apprends (utilise `@debug`/`@autopsy`).
3. **Le téléphone est ton cahier de brouillon.** Chaque leçon finit par une capture
   adb — si la capture n'est pas belle, la leçon n'est pas finie.
