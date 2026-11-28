"""CLI serveur pour basculer entre le mode AGLC (tons) et le mode assonance (intuitif).

Usage depuis le dossier `cerveau` (ex. dans l'invite de commande Railway) :
    python -m app.sandbox.orthography aglc
    python -m app.sandbox.orthography intuitive
    python -m app.sandbox.orthography status
"""

from __future__ import annotations

import sys

from app.sandbox.language import ALLOWED_ORTHOGRAPHIES, get_orthography_mode, set_orthography_mode


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0].lower() in {"status", "get", "show"}:
        print(f"orthography={get_orthography_mode()}")
        return 0

    mode = args[0].strip().lower()
    if mode not in ALLOWED_ORTHOGRAPHIES:
        print(
            f"Mode invalide: {mode!r}. Valeurs autorisées: {', '.join(sorted(ALLOWED_ORTHOGRAPHIES))}",
            file=sys.stderr,
        )
        return 2

    applied = set_orthography_mode(mode)
    print(f"orthography={applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
