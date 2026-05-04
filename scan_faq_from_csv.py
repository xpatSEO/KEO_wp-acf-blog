import argparse
import csv
import json
import os
import re
import sys


def load_rows_and_headers(path: str):
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []
    return rows, headers


def reconstruct_content(row: dict) -> str:
    """Extrait le contenu depuis content_html, content, ou content_partN."""
    for col in ("content_html", "content"):
        val = row.get(col, "") or ""
        if val.strip():
            return val
    # Chunked export support: content_part1..N
    parts = []
    for k in sorted(
        [k for k in row.keys() if k.startswith("content_part")],
        key=lambda x: int("".join(ch for ch in x if ch.isdigit()) or 0),
    ):
        v = row.get(k) or ""
        if v:
            parts.append(v)
    return "".join(parts)


ACF_BLOCK_RE = re.compile(r"<!--\s*wp:acf\\/([^\s]+)\s+(\{.*?\})\s*\/-->", re.DOTALL)


def find_acf_blocks(content: str, block_name: str):
    matches = ACF_BLOCK_RE.findall(content or "")
    out = []
    for name, json_str in matches:
        if name != block_name:
            continue
        try:
            data = json.loads(json_str)
        except Exception:
            continue
        out.append(data)
    return out


def extract_faq_from_block(block: dict):
    data = block.get("data", {}) if isinstance(block, dict) else {}
    count = None
    if "kb_faq_list" in data:
        try:
            count = int(data.get("kb_faq_list") or 0)
        except Exception:
            count = None

    questions = []
    i = 0
    while True:
        q_key = f"kb_faq_list_{i}_kb_faq_question"
        if q_key not in data:
            break
        q = data.get(q_key)
        if isinstance(q, str) and q.strip():
            questions.append(q.strip())
        i += 1

    if count is None:
        count = len(questions)

    return count, questions


def scan_faq(csv_in: str, csv_out: str):
    rows, in_headers = load_rows_and_headers(csv_in)
    computed_cols = ["has_faq", "faq_count", "questions"]
    fieldnames = list(in_headers) + [c for c in computed_cols if c not in in_headers]

    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        hits = 0
        for r in rows:
            content = reconstruct_content(r)
            blocks = find_acf_blocks(content, "faq-post-new")
            faq_count = 0
            questions_all = []
            for b in blocks:
                c, qs = extract_faq_from_block(b)
                faq_count += c or 0
                questions_all.extend(qs or [])
            has_faq = faq_count > 0 or bool(blocks)
            if has_faq:
                hits += 1

            out_row = dict(r)
            out_row["has_faq"] = str(has_faq).lower()
            out_row["faq_count"] = faq_count
            out_row["questions"] = "; ".join(questions_all[:50])
            writer.writerow(out_row)

    print(f"Scanned {len(rows)} rows; found FAQ in {hits} rows. -> {csv_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scanne un CSV pour détecter les blocs FAQ ACF et génère un rapport."
    )
    parser.add_argument("csv_input", help="CSV à scanner (source ou output de csv_to_wordpress)")
    parser.add_argument("-o", "--output", help="CSV de sortie (défaut: <input>_faq_report.csv)")

    args = parser.parse_args()

    if not os.path.exists(args.csv_input):
        print(f"[ERREUR] Fichier introuvable: {args.csv_input}")
        sys.exit(1)

    base, ext = os.path.splitext(args.csv_input)
    csv_out = args.output or f"{base}_faq_report.csv"
    scan_faq(args.csv_input, csv_out)
