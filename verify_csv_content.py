import argparse
import csv
import os
import sys
import unicodedata


def normalize_title(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    return s.strip().lower()


def load_csv_rows(path: str):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def reconstruct_content(row: dict) -> str:
    """Extrait le contenu depuis content_html, content, ou content_partN."""
    for col in ("content_html", "content"):
        val = row.get(col, "") or ""
        if val.strip():
            return val
    parts = []
    for k in sorted(
        [k for k in row.keys() if k.startswith("content_part")],
        key=lambda x: int("".join(ch for ch in x if ch.isdigit()) or 0),
    ):
        v = row.get(k) or ""
        if v:
            parts.append(v)
    return "".join(parts)


def verify_file(path: str, targets_norm: list):
    rows = load_csv_rows(path)
    print(f"\nFile: {path}  (rows={len(rows)})")
    index = {}
    for i, r in enumerate(rows):
        title = r.get("title", "")
        index.setdefault(normalize_title(title), []).append((i, r))

    if not targets_norm:
        # Pas de titres spécifiés : afficher un résumé global
        print(f"  Colonnes: {', '.join(rows[0].keys()) if rows else 'N/A'}")
        content_col = "content_html" if rows and "content_html" in rows[0] else "content"
        non_empty = sum(1 for r in rows if (r.get(content_col, "") or "").strip())
        print(f"  Lignes avec contenu ({content_col}): {non_empty}/{len(rows)}")
        return

    for orig_title, norm_title in targets_norm:
        matches = index.get(norm_title, [])
        if not matches:
            print(f"- Title: {orig_title}\n  status: NOT FOUND")
            continue
        print(f"- Title: {orig_title}\n  status: FOUND {len(matches)} row(s)")
        for i, row in matches:
            content = reconstruct_content(row)
            eff_len = len(content or "")
            meta_len = row.get("content_len")
            truncated = row.get("content_truncated")
            print(f"  - row_index: {i}")
            print(f"    content_len: {eff_len}")
            if meta_len is not None:
                try:
                    print(f"    content_len_meta: {int(meta_len)}")
                except Exception:
                    print(f"    content_len_meta: {meta_len}")
            if truncated is not None:
                print(f"    content_truncated: {truncated}")
            snippet = (content or "").replace("\n", " ")[:200]
            print(f"    snippet: {snippet}{'...' if eff_len > 200 else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Vérifie l'intégrité du contenu d'un CSV (présence d'articles, taille du content_html)."
    )
    parser.add_argument("csv_input", help="CSV à vérifier")
    parser.add_argument(
        "titles", nargs="*",
        help="Titres d'articles à rechercher (si aucun: affiche un résumé global)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.csv_input):
        print(f"[ERREUR] Fichier introuvable: {args.csv_input}")
        sys.exit(1)

    targets_norm = [(t, normalize_title(t)) for t in args.titles]
    verify_file(args.csv_input, targets_norm)
