import csv
import json
import os
import re
import sys
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup

# CONFIGURATION ACF (reprise du script existant)
ACF_MAP = {
    "summary": {
        "title": "field_66f27cb7077d9",
        "items": "field_66f27cf42734c",
        "count": "field_66f27cdc2734b"
    },
    "information": {
        "type": "field_66dea9968a05f",
        "title": "field_66daf784c9ccb",
        "image": "field_66db00fecea01",
        "content": "field_66daf784ca11e"
    },
    "tableau": {
        "titre_groupe": "field_66fe4d94b2816",
        "titre_texte": "field_66fe4f2d75d1b",
        "titre_bg": "field_66fe4ee375d19",
        "titre_color": "field_66fe4ee775d1a",
        "lignes_count": "field_66fd6a2b654a2",
        "col_count": "field_66fd6a07654a1",
        "text": "field_66fd6a37654a3",
        "bg_color": "field_66fe4fa1a7a45",
        "text_color": "field_66fd6d7e8e2a1"
    },
    "faq": {
        "title": "field_67b6ed25aa503",
        "mode": "field_67b6edc3ee572",
        "question": "field_67b6ecddaa500",
        "answer": "field_67b6ecefaa501",
        "list": "field_67b6ec8faa4ff"
    },
    "sources": {
        "title": "field_66ffa2525f0fb",
        "list": "field_66ffa2525f536",
        "link_obj": "field_66ffa25260c1f"
    }
}

TABLE_STYLES = {
    "header_bg": "#EEEEEE",
    "header_text": "#000000",
    "row_colors": ["#d9e5ff", "#c4d3ff", "#aac4ff", "#7b99d8"]
}

def encode_html_unicode(text):
    """Encode les balises HTML en Unicode et échappe les slashes"""
    if not isinstance(text, str):
        return text
    return (text
            .replace('"', '\\u0022')
            .replace('<', '\\u003c')
            .replace('>', '\\u003e')
            .replace('/', '\\/'))

def encode_dict_recursive(obj):
    """Encode récursivement les valeurs d'un dict/list"""
    if isinstance(obj, dict):
        return {k: encode_dict_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [encode_dict_recursive(item) for item in obj]
    elif isinstance(obj, str):
        return encode_html_unicode(obj)
    else:
        return obj

def build_acf_block(block_name, data_content):
    """Wrapper générique pour bloc ACF avec encodage WordPress"""
    # Encode les données
    data_encoded = encode_dict_recursive(data_content)

    # Génère le JSON avec slash échappé dans le name
    json_data = json.dumps(
        {"name": f"acf/{block_name}", "data": data_encoded, "mode": "edit"},
        ensure_ascii=False
    ).replace('"name": "acf/', '"name": "acf\\/')

    # Échappe le nom du bloc dans le commentaire
    return f'<!-- wp:acf\\/{block_name} {json_data} /-->'

def _escape_html(text: str) -> str:
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def markdown_to_html(md: str) -> str:
    """Conversion Markdown → HTML couvrant les cas courants sans dépendances externes.

    Gère: titres (#), listes (-, * et 1.), paragraphes, emphase (*, **), liens, images,
    citations (>), code inline `code`, blocs code ```lang, et blocs simples.
    """
    import re

    lines = md.splitlines()
    out = []
    in_code = False
    code_lang = ''
    code_buf = []
    in_ul = False
    in_ol = False
    in_blockquote = False
    p_buf = []

    def flush_paragraph():
        nonlocal p_buf
        if p_buf:
            text = ' '.join(p_buf).strip()
            if text:
                out.append(f'<p>{_apply_inline(text)}</p>')
            p_buf = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append('</ul>')
            in_ul = False
        if in_ol:
            out.append('</ol>')
            in_ol = False

    def close_blockquote():
        nonlocal in_blockquote
        if in_blockquote:
            # Fermer paragraphe éventuel avant de fermer blockquote
            flush_paragraph()
            out.append('</blockquote>')
            in_blockquote = False

    def _apply_inline(text: str) -> str:
        # Protéger le code inline
        code_spans = []
        def repl_code(m):
            idx = len(code_spans)
            code_spans.append(_escape_html(m.group(1)))
            return f'%%CODE{idx}%%'

        text2 = re.sub(r'`([^`]+)`', repl_code, text)
        # Images ![alt](src "title")
        text2 = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]+)")?\)',
                       lambda m: f'<img src="{m.group(2)}" alt="{_escape_html(m.group(1))}"' + (f' title="{_escape_html(m.group(3))}"' if m.group(3) else '') + '/>',
                       text2)
        # Liens [text](url "title")
        text2 = re.sub(r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]+)")?\)',
                       lambda m: f'<a href="{m.group(2)}"' + (f' title="{_escape_html(m.group(3))}"' if m.group(3) else '') + f'>{_escape_html(m.group(1))}</a>',
                       text2)
        # Gras **text** ou __text__
        text2 = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text2)
        text2 = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text2)
        # Italique *text* ou _text_
        text2 = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text2)
        text2 = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', text2)
        # Restaurer code inline
        for i, code_html in enumerate(code_spans):
            text2 = text2.replace(f'%%CODE{i}%%', f'<code>{code_html}</code>')
        return text2

    for raw in lines:
        line = raw.rstrip('\n')

        # Blocs code
        if line.strip().startswith('```'):
            fence = line.strip()
            if not in_code:
                # Ouvrir bloc
                flush_paragraph()
                close_lists()
                close_blockquote()
                code_lang = fence[3:].strip()
                code_buf = []
                in_code = True
            else:
                # Fermer bloc
                code_html = '\n'.join(_escape_html(l) for l in code_buf)
                cls = f' class="language-{code_lang}"' if code_lang else ''
                out.append(f'<pre><code{cls}>{code_html}</code></pre>')
                in_code = False
                code_lang = ''
            continue

        if in_code:
            code_buf.append(line)
            continue

        # Titres
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            flush_paragraph()
            close_lists()
            close_blockquote()
            level = len(m.group(1))
            text = m.group(2).strip()
            out.append(f'<h{level}>{_apply_inline(text)}</h{level}>')
            continue

        # Citations
        if line.strip().startswith('>'):
            if not in_blockquote:
                flush_paragraph()
                close_lists()
                out.append('<blockquote>')
                in_blockquote = True
            quote_text = line.strip()[1:].lstrip()
            if quote_text:
                p_buf.append(quote_text)
            else:
                flush_paragraph()
            continue
        else:
            if in_blockquote and (not line.strip()):
                # Ligne vide ⇒ fin de paragraphe dans la citation
                flush_paragraph()
                continue
            if in_blockquote and line.strip() and not line.strip().startswith('>'):
                # Sortie de citation
                close_blockquote()

        # Listes
        if re.match(r'^\s*[-*+]\s+.+', line):
            flush_paragraph()
            if not in_ul:
                close_lists()
                out.append('<ul>')
                in_ul = True
            item = re.sub(r'^\s*[-*+]\s+', '', line)
            out.append(f'<li>{_apply_inline(item)}</li>')
            continue
        elif re.match(r'^\s*\d+[\.)]\s+.+', line):
            flush_paragraph()
            if not in_ol:
                close_lists()
                out.append('<ol>')
                in_ol = True
            item = re.sub(r'^\s*\d+[\.)]\s+', '', line)
            out.append(f'<li>{_apply_inline(item)}</li>')
            continue
        else:
            # Fin de liste si ligne normale ou vide
            if line.strip() == '':
                flush_paragraph()
                close_lists()
                continue

        # Paragraphe
        if line.strip():
            p_buf.append(line.strip())
        else:
            flush_paragraph()

    # Fin fichier: fermer les blocs ouverts
    if in_code:
        code_html = '\n'.join(_escape_html(l) for l in code_buf)
        cls = f' class="language-{code_lang}"' if code_lang else ''
        out.append(f'<pre><code{cls}>{code_html}</code></pre>')
    flush_paragraph()
    close_lists()
    close_blockquote()
    return '\n'.join(out)

def _explode_html_with_placeholders(html_str, placeholder_map):
    """Découpe un HTML contenant des placeholders en une séquence de blocs.

    - Conserve le HTML autour des placeholders dans des blocs `wp:html`.
    - Remplace chaque placeholder par le bloc ACF correspondant.
    """
    blocks = []
    remaining = html_str

    # Recherche séquentielle du prochain placeholder, en respectant l'ordre d'apparition
    while True:
        next_pos = None
        next_key = None
        next_token = None
        for pid in placeholder_map.keys():
            token = f'<div>{pid}</div>'
            idx = remaining.find(token)
            if idx != -1 and (next_pos is None or idx < next_pos):
                next_pos = idx
                next_key = pid
                next_token = token

        if next_pos is None:
            # Plus aucun placeholder, push le reste si non vide
            if remaining.strip():
                blocks.append(f'<!-- wp:html -->\n{remaining}\n<!-- /wp:html -->')
            break

        # Partie avant le placeholder
        before = remaining[:next_pos]
        if before.strip():
            blocks.append(f'<!-- wp:html -->\n{before}\n<!-- /wp:html -->')

        # Le bloc ACF correspondant
        blocks.append(placeholder_map[next_key])

        # Reste à traiter
        remaining = remaining[next_pos + len(next_token):]

    return blocks

def html_table_to_acf(table_tag):
    """Convertit une table HTML en bloc ACF tableau"""
    rows = []
    for tr in table_tag.find_all('tr'):
        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
        if cells:
            rows.append(cells)

    if not rows:
        return None

    # Première ligne = headers
    headers = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []

    all_rows = [headers] + data_rows

    acf_data = {
        "titre_bg_color": TABLE_STYLES['header_bg'],
        "_titre_bg_color": ACF_MAP['tableau']['titre_bg'],
        "titre_text_color": TABLE_STYLES['header_text'],
        "_titre_text_color": ACF_MAP['tableau']['titre_color'],
        "titre_texte": '<p style="text-align: center;">Tableau récapitulatif</p>',
        "_titre_texte": ACF_MAP['tableau']['titre_texte'],
        "titre": "",
        "_titre": ACF_MAP['tableau']['titre_groupe'],
        "lignes": len(all_rows),
        "_lignes": ACF_MAP['tableau']['lignes_count']
    }

    for r_idx, row in enumerate(all_rows):
        bg_color = TABLE_STYLES['row_colors'][r_idx % len(TABLE_STYLES['row_colors'])]
        acf_data[f"lignes_{r_idx}_colonnes"] = len(row)
        acf_data[f"_lignes_{r_idx}_colonnes"] = ACF_MAP['tableau']['col_count']

        for c_idx, cell_text in enumerate(row):
            prefix = f"lignes_{r_idx}_colonnes_{c_idx}"
            formatting = "<strong>" if r_idx == 0 else ""
            formatting_end = "</strong>" if r_idx == 0 else ""
            html_text = f'<p style="text-align: center;">{formatting}{cell_text}{formatting_end}</p>'

            acf_data[f"{prefix}_texte"] = html_text
            acf_data[f"_{prefix}_texte"] = ACF_MAP['tableau']['text']
            acf_data[f"{prefix}_bg_color"] = bg_color
            acf_data[f"_{prefix}_bg_color"] = ACF_MAP['tableau']['bg_color']
            acf_data[f"{prefix}_text_color"] = "#000000"
            acf_data[f"_{prefix}_text_color"] = ACF_MAP['tableau']['text_color']

    return build_acf_block("tableau", acf_data)

def keypoints_to_summary_acf(keypoints_html):
    """Convertit la colonne keypoints (liste HTML) en bloc ACF summary"""
    if not keypoints_html or keypoints_html.strip() == '':
        return None

    soup = BeautifulSoup(keypoints_html, 'html.parser')
    list_tag = soup.find(['ol', 'ul'])

    if not list_tag:
        return None

    # Extrait les items - garde le HTML interne (strong, etc.)
    items = []
    for li in list_tag.find_all('li', recursive=False):
        # Garde le HTML interne de chaque <li>
        item_html = ''.join(str(child) for child in li.children)
        items.append(item_html.strip())

    if not items:
        return None

    acf_data = {
        "title": "En résumé :",
        "_title": ACF_MAP['summary']['title'],
        "summary": len(items),
        "_summary": ACF_MAP['summary']['count']
    }

    for i, item in enumerate(items):
        acf_data[f"summary_{i}_item"] = item
        acf_data[f"_summary_{i}_item"] = ACF_MAP['summary']['items']

    return build_acf_block("summary", acf_data)

def generate_summary_from_meta_and_h2(metadescription, html_content, max_h2=3):
    """Fallback summary: bullet 1 = metadescription, bullets 2..N = premiers H2.

    Utilisé quand la colonne `keypoints` est absente et qu'aucune <div class="summary">
    n'existe dans le HTML. Renvoie None si moins de 2 items exploitables.
    """
    items = []
    if metadescription and str(metadescription).strip():
        items.append(str(metadescription).strip())

    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        for h2 in soup.find_all('h2')[:max_h2]:
            text = h2.get_text(strip=True)
            if text:
                items.append(text)

    if len(items) < 2:
        return None

    acf_data = {
        "title": "En résumé :",
        "_title": ACF_MAP['summary']['title'],
        "summary": len(items),
        "_summary": ACF_MAP['summary']['count']
    }

    for i, item in enumerate(items):
        acf_data[f"summary_{i}_item"] = item
        acf_data[f"_summary_{i}_item"] = ACF_MAP['summary']['items']

    return build_acf_block("summary", acf_data)

def div_summary_to_acf(div_tag):
    """Convertit une <div class="summary"> avec liste en bloc ACF summary"""
    title_tag = div_tag.find(['h4', 'h3', 'h2', 'strong', 'b'])
    title = title_tag.get_text(strip=True) if title_tag else "En bref :"

    # Trouve la liste <ul> ou <ol>
    list_tag = div_tag.find(['ul', 'ol'])
    if not list_tag:
        return None

    items = [li.get_text(strip=True) for li in list_tag.find_all('li')]
    if not items:
        return None

    acf_data = {
        "title": title,
        "_title": ACF_MAP['summary']['title'],
        "summary": len(items),
        "_summary": ACF_MAP['summary']['count']
    }

    for i, item in enumerate(items):
        acf_data[f"summary_{i}_item"] = item
        acf_data[f"_summary_{i}_item"] = ACF_MAP['summary']['items']

    return build_acf_block("summary", acf_data)

def dl_to_faq_acf(dl_tag):
    """Convertit une <dl> (definition list) en bloc ACF FAQ"""
    questions = dl_tag.find_all('dt')
    answers = dl_tag.find_all('dd')

    if not questions or len(questions) != len(answers):
        return None

    faq_items = []
    for q, a in zip(questions, answers):
        faq_items.append({
            "question": q.get_text(strip=True),
            "answer": a.get_text(strip=True)
        })

    acf_data = {
        "kb_faq_title": "FAQ :",
        "_kb_faq_title": ACF_MAP['faq']['title'],
        "kb_faq_mode": "multiple",
        "_kb_faq_mode": ACF_MAP['faq']['mode']
    }

    for i, item in enumerate(faq_items):
        acf_data[f"kb_faq_list_{i}_kb_faq_question"] = item['question']
        acf_data[f"_kb_faq_list_{i}_kb_faq_question"] = ACF_MAP['faq']['question']
        acf_data[f"kb_faq_list_{i}_kb_faq_answer"] = item['answer']
        acf_data[f"_kb_faq_list_{i}_kb_faq_answer"] = ACF_MAP['faq']['answer']

    # Le count à la fin
    acf_data["kb_faq_list"] = len(faq_items)
    acf_data["_kb_faq_list"] = ACF_MAP['faq']['list']

    return build_acf_block("faq-post-new", acf_data)

def div_faq_to_acf(div_tag):
    """Convertit une <div class="faq"> avec questions/réponses en bloc ACF FAQ"""
    faq_items = []

    # Pattern 1 : <div class="faq-item"><h4>Question</h4><p>Réponse</p></div>
    faq_item_divs = div_tag.find_all('div', class_='faq-item')
    if faq_item_divs:
        for item_div in faq_item_divs:
            question_tag = item_div.find(['h4', 'h3', 'h5', 'strong'])
            answer_tag = item_div.find('p')
            if question_tag and answer_tag:
                faq_items.append({
                    "question": question_tag.get_text(strip=True),
                    "answer": answer_tag.get_text(strip=True)
                })
    else:
        # Pattern 2 : alternance <h4>Question</h4><p>Réponse</p>
        # Filtre les nœuds texte (NavigableString) pour ne garder que les éléments HTML
        children = [c for c in div_tag.children if hasattr(c, 'name') and c.name]
        i = 0
        while i < len(children) - 1:
            elem = children[i]
            next_elem = children[i + 1]
            if elem.name in ['h3', 'h4', 'h5'] and next_elem.name == 'p':
                faq_items.append({
                    "question": elem.get_text(strip=True),
                    "answer": next_elem.get_text(strip=True)
                })
                i += 2
            else:
                i += 1

    if not faq_items:
        return None

    acf_data = {
        "kb_faq_title": "FAQ :",
        "_kb_faq_title": ACF_MAP['faq']['title'],
        "kb_faq_mode": "multiple",
        "_kb_faq_mode": ACF_MAP['faq']['mode']
    }

    for i, item in enumerate(faq_items):
        acf_data[f"kb_faq_list_{i}_kb_faq_question"] = item['question']
        acf_data[f"_kb_faq_list_{i}_kb_faq_question"] = ACF_MAP['faq']['question']
        acf_data[f"kb_faq_list_{i}_kb_faq_answer"] = item['answer']
        acf_data[f"_kb_faq_list_{i}_kb_faq_answer"] = ACF_MAP['faq']['answer']

    # Le count à la fin
    acf_data["kb_faq_list"] = len(faq_items)
    acf_data["_kb_faq_list"] = ACF_MAP['faq']['list']

    return build_acf_block("faq-post-new", acf_data)

def div_faq_accordion_to_acf(div_tag):
    """Convertit un accordéon FAQ HTML (ex: .faq-accordion/.faq-item/.faq-toggle/.faq-content) en bloc ACF FAQ"""
    faq_items = []

    # Cas principal: items explicites
    items = div_tag.find_all(class_=lambda c: c and ('faq-item' in c))
    if items:
        for item in items:
            # Question: dans .faq-toggle span/h3/h4/button
            toggle = item.find(class_=lambda c: c and ('faq-toggle' in c))
            q_text = None
            if toggle:
                q_tag = toggle.find(['span', 'h3', 'h4', 'button']) or toggle
                q_text = q_tag.get_text(strip=True) if q_tag else None
            if not q_text:
                q_tag = item.find(['h3', 'h4', 'summary'])
                q_text = q_tag.get_text(strip=True) if q_tag else None

            # Réponse: dans .faq-content sinon 1er <p>
            content = item.find(class_=lambda c: c and ('faq-content' in c))
            if content:
                a_text = content.get_text(" ", strip=True)
            else:
                p = item.find('p')
                a_text = p.get_text(" ", strip=True) if p else ''

            if q_text and a_text:
                faq_items.append({"question": q_text, "answer": a_text})

    # Fallback: boutons .faq-toggle successifs suivis d'un conteneur .faq-content
    if not faq_items:
        toggles = div_tag.find_all(class_=lambda c: c and ('faq-toggle' in c))
        for tog in toggles:
            q_tag = tog.find(['span', 'h3', 'h4', 'button']) or tog
            q_text = q_tag.get_text(strip=True) if q_tag else None
            # Trouver le sibling .faq-content
            content = tog.find_next_sibling(class_=lambda c: c and ('faq-content' in c))
            a_text = content.get_text(" ", strip=True) if content else ''
            if q_text and a_text:
                faq_items.append({"question": q_text, "answer": a_text})

    if not faq_items:
        return None

    acf_data = {
        "kb_faq_title": "FAQ :",
        "_kb_faq_title": ACF_MAP['faq']['title'],
        "kb_faq_mode": "multiple",
        "_kb_faq_mode": ACF_MAP['faq']['mode']
    }

    for i, item in enumerate(faq_items):
        acf_data[f"kb_faq_list_{i}_kb_faq_question"] = item['question']
        acf_data[f"_kb_faq_list_{i}_kb_faq_question"] = ACF_MAP['faq']['question']
        acf_data[f"kb_faq_list_{i}_kb_faq_answer"] = item['answer']
        acf_data[f"_kb_faq_list_{i}_kb_faq_answer"] = ACF_MAP['faq']['answer']

    acf_data["kb_faq_list"] = len(faq_items)
    acf_data["_kb_faq_list"] = ACF_MAP['faq']['list']

    return build_acf_block("faq-post-new", acf_data)

def div_sources_to_acf(div_tag):
    """Convertit une <div class="sources"> avec liste de liens en bloc ACF sources"""
    # Trouve tous les liens
    links = div_tag.find_all('a')
    if not links:
        return None

    sources = []
    for link in links:
        title = link.get_text(strip=True)
        url = link.get('href', '')
        if title and url:
            sources.append({"title": title, "url": url})

    if not sources:
        return None

    acf_data = {
        "title": "Sources :",
        "_title": ACF_MAP['sources']['title'],
        "sources": len(sources),
        "_sources": ACF_MAP['sources']['list']
    }

    for i, item in enumerate(sources):
        link_obj = {"title": item['title'], "url": item['url'], "target": "_blank"}
        acf_data[f"sources_{i}_lien"] = link_obj
        acf_data[f"_sources_{i}_lien"] = ACF_MAP['sources']['link_obj']

    return build_acf_block("sources", acf_data)

def div_note_to_acf(div_tag):
    """Convertit une <div class="note/advice/attention"> en bloc ACF information"""
    # Copie pour ne pas modifier l'original
    div_copy = BeautifulSoup(str(div_tag), 'html.parser')

    # Extraire le titre
    title_tag = div_copy.find(['h4', 'h3', 'h2'])
    title = title_tag.get_text(strip=True) if title_tag else "Information"

    # Déterminer le type depuis le titre
    title_lower = title.lower()
    if 'attention' in title_lower or 'alerte' in title_lower:
        info_type = "attention"
    else:
        info_type = "bon-a-savoir"

    # Supprimer le titre du contenu
    if title_tag:
        title_tag.decompose()

    # Récupérer uniquement le contenu INTERNE (sans la div wrapper)
    # On prend tous les enfants de la div
    content_parts = []
    for child in div_copy.find().children:
        if hasattr(child, 'name') and child.name:  # C'est un tag HTML
            content_parts.append(str(child))
        elif child.strip():  # C'est du texte
            content_parts.append(str(child))

    content = ''.join(content_parts).strip()

    acf_data = {
        "type_information": info_type,
        "_type_information": ACF_MAP['information']['type'],
        "title": title,
        "_title": ACF_MAP['information']['title'],
        "content": content,
        "_content": ACF_MAP['information']['content'],
        "image": "",
        "_image": ACF_MAP['information']['image']
    }

    return build_acf_block("information", acf_data)

def detect_faq_section_heuristic(soup):
    """Détection heuristique d'une section FAQ :
    - H2 avec mot-clé FAQ/Questions
    - Suivi de plusieurs H3/H4 (questions) + P (réponses)
    - OU derniers H3/H4 avec "?" (>= 2)

    Returns: (start_index, end_index, faq_items) ou None
    """
    all_elements = list(soup.children)
    faq_keywords = ['faq', 'questions fréquentes', 'questions courantes', 'questions/réponses']

    # MÉTHODE 1: Cherche un H2 avec mot-clé FAQ
    for i, elem in enumerate(all_elements):
        if elem.name is None:
            continue

        if elem.name == 'h2':
            title_text = elem.get_text(strip=True).lower()
            if any(keyword in title_text for keyword in faq_keywords):
                # Analyse les éléments suivants
                faq_items = []
                j = i + 1
                current_question = None

                while j < len(all_elements):
                    next_elem = all_elements[j]
                    if next_elem.name is None:
                        j += 1
                        continue

                    # Si on trouve un nouveau H2, la section FAQ est terminée
                    if next_elem.name == 'h2':
                        break

                    # H3/H4 = Question
                    if next_elem.name in ['h3', 'h4']:
                        question_text = next_elem.get_text(strip=True)
                        # Vérifie que ça ressemble à une question
                        if '?' in question_text or question_text.lower().startswith(('comment', 'pourquoi', 'quand', 'où', 'qui', 'quel', 'combien', 'peut-on', 'faut-il', 'dois-je')):
                            current_question = question_text

                    # P après une question = Réponse
                    elif next_elem.name == 'p' and current_question:
                        answer_text = next_elem.get_text(strip=True)
                        if answer_text:
                            faq_items.append({
                                "question": current_question,
                                "answer": answer_text
                            })
                            current_question = None

                    j += 1

                # Si on a au moins 2 questions, c'est une FAQ valide
                if len(faq_items) >= 2:
                    return (i, j, faq_items)

    # MÉTHODE 2: Cherche les H3/H4 avec "?" GROUPÉS À LA FIN
    headings_with_q = []
    for i, elem in enumerate(all_elements):
        if elem.name in ['h3', 'h4']:
            text = elem.get_text(strip=True)
            if '?' in text:
                headings_with_q.append((i, elem, text))

    # Si on a au moins 2 H3/H4 avec "?", trouver le groupe le plus vers la fin
    if len(headings_with_q) >= 2:
        # Identifier les groupes de H3/H4 consécutifs (max 5 éléments entre chaque)
        groups = []
        current_group = [headings_with_q[0]]

        for i in range(1, len(headings_with_q)):
            prev_idx = headings_with_q[i-1][0]
            curr_idx = headings_with_q[i][0]

            # Si l'écart est <= 5 éléments, même groupe
            if curr_idx - prev_idx <= 5:
                current_group.append(headings_with_q[i])
            else:
                # Nouveau groupe
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = [headings_with_q[i]]

        # Ajouter le dernier groupe
        if len(current_group) >= 2:
            groups.append(current_group)

        # Prendre le dernier groupe (celui le plus vers la fin)
        if groups:
            faq_group = groups[-1]
            faq_items = []
            start_idx = faq_group[0][0]
            end_idx = len(all_elements)

            for idx, h_elem, question in faq_group:
                # Chercher le paragraphe suivant comme réponse
                answer_parts = []
                j = idx + 1
                while j < len(all_elements):
                    next_elem = all_elements[j]
                    if next_elem.name is None:
                        j += 1
                        continue
                    # Stop si on trouve un nouveau heading
                    if next_elem.name in ['h2', 'h3', 'h4']:
                        break
                    # Collecter les paragraphes
                    if next_elem.name == 'p':
                        answer_parts.append(next_elem.get_text(strip=True))
                    j += 1

                if answer_parts:
                    faq_items.append({
                        "question": question,
                        "answer": ' '.join(answer_parts)
                    })

            if len(faq_items) >= 2:
                return (start_idx, end_idx, faq_items)

    return None

def parse_html_to_gutenberg(html_content):
    """Parse le HTML et convertit les blocs spéciaux en ACF"""
    soup = BeautifulSoup(html_content, 'html.parser')
    gutenberg_blocks = []

    # ÉTAPE 1: Convertir toutes les tables (même imbriquées) en blocs ACF
    # et les remplacer par un placeholder
    table_placeholders = {}
    for table_idx, table in enumerate(soup.find_all('table')):
        placeholder_id = f"___TABLE_PLACEHOLDER_{table_idx}___"
        acf_block = html_table_to_acf(table)
        if acf_block:
            table_placeholders[placeholder_id] = acf_block
            # Remplacer la table par un placeholder
            placeholder_tag = soup.new_tag('div')
            placeholder_tag.string = placeholder_id
            table.replace_with(placeholder_tag)

    # ÉTAPE 2: Convertir toutes les divs info/note/advice (même imbriquées)
    info_placeholders = {}
    info_classes = ['note', 'information', 'alert', 'warning', 'attention', 'advice']
    # class_=list en bs4 signifie "toutes ces classes". On veut "au moins une" → utiliser un prédicat
    for div_idx, div in enumerate(soup.find_all('div', class_=lambda c: c and any(cls in c for cls in info_classes))):
        placeholder_id = f"___INFO_PLACEHOLDER_{div_idx}___"
        acf_block = div_note_to_acf(div)
        if acf_block:
            info_placeholders[placeholder_id] = acf_block
            # Remplacer la div par un placeholder
            placeholder_tag = soup.new_tag('div')
            placeholder_tag.string = placeholder_id
            div.replace_with(placeholder_tag)

    all_elements = list(soup.children)

    # Détection heuristique des FAQ
    faq_section = detect_faq_section_heuristic(soup)
    faq_start_idx = faq_section[0] if faq_section else None
    faq_end_idx = faq_section[1] if faq_section else None
    faq_items = faq_section[2] if faq_section else None

    # Parcourt les éléments de premier niveau
    for idx, element in enumerate(all_elements):
        if element.name is None:  # Texte brut
            continue

        acf_block = None

        # Si on est dans une section FAQ détectée, on skip jusqu'à la fin
        if faq_start_idx is not None and faq_start_idx <= idx < faq_end_idx:
            # Au premier élément de la FAQ, on génère le bloc ACF
            if idx == faq_start_idx:
                acf_data = {
                    "kb_faq_title": "FAQ :",
                    "_kb_faq_title": ACF_MAP['faq']['title'],
                    "kb_faq_mode": "multiple",
                    "_kb_faq_mode": ACF_MAP['faq']['mode']
                }

                for i, item in enumerate(faq_items):
                    acf_data[f"kb_faq_list_{i}_kb_faq_question"] = item['question']
                    acf_data[f"_kb_faq_list_{i}_kb_faq_question"] = ACF_MAP['faq']['question']
                    acf_data[f"kb_faq_list_{i}_kb_faq_answer"] = item['answer']
                    acf_data[f"_kb_faq_list_{i}_kb_faq_answer"] = ACF_MAP['faq']['answer']

                # Le count à la fin
                acf_data["kb_faq_list"] = len(faq_items)
                acf_data["_kb_faq_list"] = ACF_MAP['faq']['list']

                gutenberg_blocks.append(build_acf_block("faq-post-new", acf_data))
            continue

        # Cas spécial : DL (definition list) → ACF FAQ
        if element.name == 'dl':
            acf_block = dl_to_faq_acf(element)

        # Cas spéciaux pour DIV avec classes
        elif element.name == 'div':
            classes = element.get('class', [])

            # DIV.summary ou DIV.en-bref → ACF Summary
            if any(cls in ['summary', 'en-bref', 'encadre'] for cls in classes):
                acf_block = div_summary_to_acf(element)

            # DIV.faq → ACF FAQ
            elif 'faq' in classes:
                acf_block = div_faq_to_acf(element)

            # Accordéon FAQ (.faq-accordion / .faq-item / .faq-toggle)
            elif any('faq-accordion' in cls or 'accordion' in cls for cls in classes) or element.find(class_=lambda c: c and ('faq-item' in c or 'faq-toggle' in c)):
                acf_block = div_faq_accordion_to_acf(element)

            # DIV.sources ou DIV.references → ACF Sources
            elif any(cls in ['sources', 'references', 'liens'] for cls in classes):
                acf_block = div_sources_to_acf(element)

            # DIV.note ou DIV.information → ACF Information
            elif any(cls in ['note', 'information', 'alert', 'warning', 'attention', 'advice'] for cls in classes):
                acf_block = div_note_to_acf(element)

        # Si un bloc ACF a été généré, l'ajouter
        if acf_block:
            gutenberg_blocks.append(acf_block)
        else:
            # Vérifier si c'est un placeholder (table ou info) en tant que nœud isolé
            element_text = element.get_text(strip=True)
            if element_text in table_placeholders:
                gutenberg_blocks.append(table_placeholders[element_text])
            elif element_text in info_placeholders:
                gutenberg_blocks.append(info_placeholders[element_text])
            else:
                # Sinon : Bloc HTML standard, en insérant les blocs ACF aux emplacements des placeholders
                html_str = str(element)
                placeholder_map = {**table_placeholders, **info_placeholders}

                # Si l'élément contient des placeholders imbriqués, on découpe proprement
                if any(f'<div>{pid}</div>' in html_str for pid in placeholder_map.keys()):
                    blocks = _explode_html_with_placeholders(html_str, placeholder_map)
                    gutenberg_blocks.extend(blocks)
                else:
                    if html_str.strip():
                        gutenberg_blocks.append(f'<!-- wp:html -->\n{html_str}\n<!-- /wp:html -->')

    # Ajouter les blocs qui n'ont pas été insérés (cas où ils sont encore dans des divs)
    for placeholder_id, table_block in table_placeholders.items():
        if table_block not in gutenberg_blocks:
            gutenberg_blocks.append(table_block)
    for placeholder_id, info_block in info_placeholders.items():
        if info_block not in gutenberg_blocks:
            gutenberg_blocks.append(info_block)

    return '\n\n'.join(gutenberg_blocks)

def _get_first_nonempty(row, keys):
    for k in keys:
        if k in row and row[k] and str(row[k]).strip():
            return row[k]
    return ""


def _short(s, n=120):
    s = (s or "")
    s = s.replace('\n', ' ').replace('\r', ' ')
    return (s[:n] + ('…' if len(s) > n else ''))

def rewrite_internal_links(html: str) -> str:
    """Réécrit les liens internes keobiz.fr pour pointer vers /le-mag/slug

    Règle:
    - Si lien vers keobiz.fr ou relatif '/...'
    - Si le chemin n'est PAS vide et n'est PAS déjà '/le-mag/...'
    - Si le chemin est un slug simple (un seul segment): '/slug' → '/le-mag/slug'
    - Preserve query/fragment, conserve schéma/hôte si présent
    """
    if not html or '<a' not in html:
        return html
    soup = BeautifulSoup(html, 'html.parser')

    def should_rewrite_path(path: str) -> bool:
        if not path or path == '/':
            return False
        if path.startswith('/le-mag/'):
            return False
        # Normalize multiple slashes
        segs = [seg for seg in path.split('/') if seg]
        # Rewrite only single-segment slugs to be safe
        return len(segs) == 1

    for a in soup.find_all('a', href=True):
        href = a['href']
        # Handle anchors and mailto/tel
        if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
            continue
        # Relative URL
        if href.startswith('/'):
            if should_rewrite_path(href):
                segs = [seg for seg in href.split('/') if seg]
                new_path = '/le-mag/' + segs[0]
                a['href'] = new_path
            continue

        # Absolute URL
        try:
            p = urlparse(href)
        except Exception:
            continue
        host = (p.netloc or '').lower()
        if host.endswith('keobiz.fr'):
            if should_rewrite_path(p.path or ''):
                segs = [seg for seg in (p.path or '').split('/') if seg]
                new_path = '/le-mag/' + segs[0]
                new_parts = (p.scheme, p.netloc, new_path, p.params, p.query, p.fragment)
                a['href'] = urlunparse(new_parts)

    return str(soup)


def strip_imgs_without_src(html: str) -> str:
    """Supprime les balises <img> sans attribut src (ou src vide)."""
    if not html or '<img' not in html:
        return html
    soup = BeautifulSoup(html, 'html.parser')
    removed = 0
    for img in soup.find_all('img'):
        src = img.get('src')
        if src is None or str(src).strip() == '':
            img.decompose()
            removed += 1
    if removed:
        # Optionnel: on pourrait logger ici si besoin
        pass
    return str(soup)

# --- FAQ detection from generated Gutenberg ACF blocks ---
_ACF_BLOCK_RE = re.compile(r"<!--\s*wp:acf\\/([^\s]+)\s+(\{.*?\})\s*\/-->", re.DOTALL)


def _find_acf_blocks(content: str, block_name: str):
    matches = _ACF_BLOCK_RE.findall(content or "")
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


def _extract_faq_info(content: str):
    def _extract_from_html_fragment(html: str):
        soup = BeautifulSoup(html or "", 'html.parser')
        qs = []
        # Pattern 1: custom accordion: .faq-accordion > .faq-item
        acc = soup.find(class_=lambda c: c and ('faq-accordion' in c or 'faq' in c))
        if acc:
            for item in acc.find_all(class_=lambda c: c and ('faq-item' in c or 'faq-toggle' in c)):
                # Try to get question from a span/heading within the toggle or item
                q_tag = item.find(['span', 'h3', 'h4', 'button'], class_=lambda c: True) or item.find(['h3', 'h4'])
                if q_tag:
                    q_text = q_tag.get_text(strip=True)
                    if q_text:
                        qs.append(q_text)
            if qs:
                return True, len(qs), qs
        # Pattern 2: H2 contains 'faq' then H3/H4 + P pairs
        headings = soup.find_all(['h2', 'h3', 'h4'])
        start = None
        for idx, h in enumerate(headings):
            if h.name == 'h2' and 'faq' in h.get_text(strip=True).lower():
                start = h
                break
        if start:
            # Iterate siblings after h2
            for sib in start.find_all_next():
                if sib.name in ['h2']:
                    break
                if sib.name in ['h3', 'h4']:
                    qt = sib.get_text(strip=True)
                    if qt and ('?' in qt or True):
                        qs.append(qt)
            if qs:
                return True, len(qs), qs
        # Pattern 3: grouped h3/h4 with '?' marks
        grouped = []
        for h in soup.find_all(['h3', 'h4']):
            t = h.get_text(strip=True)
            if t and '?' in t:
                grouped.append(t)
        if len(grouped) >= 2:
            return True, len(grouped), grouped
        return False, 0, []

    # ACF blocks first
    blocks = _find_acf_blocks(content, "faq-post-new")
    faq_count = 0
    questions_all = []
    for b in blocks:
        data = b.get("data", {}) if isinstance(b, dict) else {}
        try:
            faq_count += int(data.get("kb_faq_list") or 0)
        except Exception:
            pass
        i = 0
        while True:
            key = f"kb_faq_list_{i}_kb_faq_question"
            if key not in data:
                break
            q = data.get(key)
            if isinstance(q, str) and q.strip():
                questions_all.append(q.strip())
            i += 1

    # Supplement with HTML blocks (wp:html) if needed
    html_fragments = []
    for m in re.finditer(r"<!--\s*wp:html\s*-->\s*(.*?)\s*<!--\s*/wp:html\s*-->", content or "", flags=re.DOTALL | re.IGNORECASE):
        html_fragments.append(m.group(1))
    # If no explicit html blocks, consider whole content as fallback (some generators inline html)
    if not html_fragments and ('<' in (content or '')):
        html_fragments = [content]
    for frag in html_fragments:
        has, cnt, qs = _extract_from_html_fragment(frag)
        if has:
            faq_count = faq_count or 0
            if cnt:
                faq_count = max(faq_count, cnt) if questions_all else faq_count + cnt
            if qs:
                questions_all.extend(qs)

    # Finalize
    if faq_count == 0 and questions_all:
        faq_count = len(questions_all)
    has_faq = (len(blocks) > 0) or faq_count > 0
    # Deduplicate questions preserving order
    seen = set()
    dedup_qs = []
    for q in questions_all:
        if q not in seen:
            seen.add(q)
            dedup_qs.append(q)
    return has_faq, faq_count, dedup_qs

def write_posts_csv(posts, output_csv_path, content_max_chars=32000):
    """Écrit un CSV en plus du JSON pour faciliter l'import/inspection.

    Colonnes exportées: title, slug, status, content, yoast_title, yoast_metadesc, tags,
    content_len, content_truncated. Le contenu est tronqué à ~32k pour compat Excel.
    """
    fieldnames = [
        "title",
        "slug",
        "status",
        "content",
        "yoast_title",
        "yoast_metadesc",
        "tags",
        "content_len",
        "content_truncated",
        "has_faq",
        "faq_count",
        "questions",
    ]

    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        truncated_count = 0
        for p in posts:
            meta = p.get("meta", {}) or {}
            tags_val = p.get("tags", [])
            if isinstance(tags_val, list):
                tags_str = ",".join(str(t) for t in tags_val)
            else:
                tags_str = str(tags_val or "")
            content_str = p.get("content", "")
            orig_len = len(content_str)
            truncated = False
            if content_max_chars is not None and orig_len > content_max_chars:
                content_str = content_str[:content_max_chars]
                truncated = True
                truncated_count += 1

            # FAQ info from full content (before truncation)
            has_faq, faq_count, questions = _extract_faq_info(p.get("content", ""))

            writer.writerow({
                "title": p.get("title", ""),
                "slug": p.get("slug", ""),
                "status": p.get("status", ""),
                "content": content_str,
                "yoast_title": meta.get("_yoast_wpseo_title", ""),
                "yoast_metadesc": meta.get("_yoast_wpseo_metadesc", ""),
                "tags": tags_str,
                "content_len": orig_len,
                "content_truncated": str(truncated).lower(),
                "has_faq": str(has_faq).lower(),
                "faq_count": faq_count,
                "questions": "; ".join(questions[:50]),
            })
        if truncated_count:
            print(f"[INFO] CSV: contenu tronqué (> {content_max_chars}) pour {truncated_count} articles (limite Excel).")


def write_posts_csv_chunked(posts, output_csv_path, chunk_size=30000, max_parts=4):
    """Écrit un CSV adapté à Excel en découpant le content en plusieurs colonnes.

    - Excel limite une cellule à ~32 767 caractères.
    - On découpe le contenu en `content_part1..N` (jusqu'à `max_parts`).
    """
    part_headers = [f"content_part{i}" for i in range(1, max_parts + 1)]
    fieldnames = [
        "title",
        "slug",
        "status",
        *part_headers,
        "yoast_title",
        "yoast_metadesc",
        "tags",
        "content_len",
        "has_faq",
        "faq_count",
        "questions",
    ]

    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        oversized = 0
        for p in posts:
            meta = p.get("meta", {}) or {}
            tags_val = p.get("tags", [])
            if isinstance(tags_val, list):
                tags_str = ",".join(str(t) for t in tags_val)
            else:
                tags_str = str(tags_val or "")
            content_str = p.get("content", "")
            orig_len = len(content_str)

            # Split en morceaux de chunk_size
            parts = [content_str[i:i+chunk_size] for i in range(0, orig_len, chunk_size)] if content_str else []
            if len(parts) > max_parts:
                oversized += 1
                parts = parts[:max_parts]

            has_faq, faq_count, questions = _extract_faq_info(content_str)

            row = {
                "title": p.get("title", ""),
                "slug": p.get("slug", ""),
                "status": p.get("status", ""),
                "yoast_title": meta.get("_yoast_wpseo_title", ""),
                "yoast_metadesc": meta.get("_yoast_wpseo_metadesc", ""),
                "tags": tags_str,
                "content_len": orig_len,
                "has_faq": str(has_faq).lower(),
                "faq_count": faq_count,
                "questions": "; ".join(questions[:50]),
            }
            for i, header in enumerate(part_headers):
                row[header] = parts[i] if i < len(parts) else ""

            writer.writerow(row)

    print(f"[INFO] CSV (chunked for Excel): écrit {output_csv_path} (chunk_size={chunk_size}, max_parts={max_parts}, oversized_rows={oversized}).")


def process_csv(csv_path, output_json_path, categories=None, tags=None, output_csv_path=None, output_csv_full_path=None, output_csv_chunked_path=None):
    """Pipeline principal : CSV → JSON WordPress

    Args:
        csv_path: Chemin vers le CSV source
        output_json_path: Chemin vers le JSON de sortie
        categories: Liste d'IDs de catégories par défaut (optionnel)
        tags: Liste d'IDs de tags par défaut (optionnel)
    """
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        # Utilise le dialecte CSV standard (comma, quote=") pour fiabilité
        # sur contenus multiline correctement quotés
        reader = csv.DictReader(f)
        posts = []

        for i, row in enumerate(reader, 1):
            # Filtrer les lignes totalement vides (souvent issues d'une rupture de quoting)
            if not row or all((v is None or str(v).strip()=="") for v in row.values()):
                continue
            # Mapping des colonnes du CSV exporté
            # Sélection stricte: content_html d'abord, sinon content_markdown
            html_content = row.get('content_html') or ''
            if html_content and html_content.strip():
                print(f"[DEBUG] Using content_html (len={len(html_content)}) -> {_short(html_content)}")
            else:
                md = row.get('content_markdown') or ''
                if md and str(md).strip():
                    print(f"[DEBUG] Fallback content_markdown (len={len(md)}) -> {_short(md)}")
                    html_content = markdown_to_html(md)
                    print(f"[DEBUG] Converted MD->HTML (len={len(html_content)}) -> {_short(html_content)}")
                else:
                    print(f"[WARN] No content_html or content_markdown for line {i} (title='{_short(title,60)}', slug='{slug}')")
                    html_content = ''
            title = _get_first_nonempty(row, ['title', 'Title', 'post_title']) or 'Sans titre'
            seo_title = _get_first_nonempty(row, ['metatitle', 'SEO_Title', 'yoast_title']) or title
            seo_desc = _get_first_nonempty(row, ['metadescription', 'SEO_Desc', 'yoast_metadesc'])
            slug = _get_first_nonempty(row, ['slug', 'post_name'])
            keypoints_html = _get_first_nonempty(row, ['keypoints', 'Keypoints'])

            if not html_content:
                # Fallback depuis Markdown si présent
                md = _get_first_nonempty(row, ['content_markdown', 'markdown'])
                if md:
                    html_content = markdown_to_html(md)
                else:
                    print(f"[WARN] Aucune colonne de contenu trouvée pour la ligne {i} (titre: '{title[:80]}'). Clés: {list(row.keys())}")

            # Nettoyage images sans src et correction des liens internes
            if html_content:
                # Enlever <img> sans src
                html_content = strip_imgs_without_src(html_content)
                before = len(html_content)
                html_content = rewrite_internal_links(html_content)
                after = len(html_content)
                if before != after:
                    print(f"[DEBUG] Links rewritten in content (len {before}->{after})")

            if keypoints_html:
                keypoints_html = strip_imgs_without_src(keypoints_html)
                keypoints_html = rewrite_internal_links(keypoints_html)

            # Parse et convertit le HTML
            print(f"[{i}] Traitement : {title[:60]}...")
            gutenberg_content = parse_html_to_gutenberg(html_content)

            # Filet de sécurité: si le parsing retourne vide, conserver le HTML source
            if (not gutenberg_content or not gutenberg_content.strip()) and (html_content and html_content.strip()):
                print(f"[WARN] Parser produced empty content; preserving raw HTML (len={len(html_content)}).")
                gutenberg_content = f'<!-- wp:html -->\n{html_content}\n<!-- /wp:html -->'

            # Génère le bloc summary depuis keypoints et l'insère au début.
            # Fallback: si pas de keypoints, on construit un summary depuis
            # metadescription + premiers H2 du contenu source.
            summary_block = keypoints_to_summary_acf(keypoints_html)
            if not summary_block:
                summary_block = generate_summary_from_meta_and_h2(seo_desc, html_content)
            if summary_block:
                gutenberg_content = summary_block + '\n\n' + gutenberg_content

            if not gutenberg_content.strip():
                raw_html = row.get('content_html') or ''
                raw_md = row.get('content_markdown') or ''
                print(f"[WARN] Still empty after fallback for: '{_short(title,80)}' (line {i}). lens -> html:{len(str(raw_html))} md:{len(str(raw_md))}")
                # Ne pas créer d'article vide
                continue

            # Structure finale pour WordPress
            wp_post = {
                "title": title,
                "slug": slug,
                "content": gutenberg_content,
                "status": "draft",
                "meta": {
                    "_yoast_wpseo_title": seo_title,
                    "_yoast_wpseo_metadesc": seo_desc
                },
                "tags": tags or []
            }

            posts.append(wp_post)

    # Sauvegarde le JSON
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

    # Sauvegarde le CSV si demandé
    if output_csv_path:
        write_posts_csv(posts, output_csv_path)
        print(f"✅ Export CSV (safe) → {output_csv_path}")
    if output_csv_full_path:
        write_posts_csv(posts, output_csv_full_path, content_max_chars=None)
        print(f"✅ Export CSV (full) → {output_csv_full_path}")
    if output_csv_chunked_path:
        write_posts_csv_chunked(posts, output_csv_chunked_path)
        print(f"✅ Export CSV (excel-chunked) → {output_csv_chunked_path}")

    print(f"\n✅ {len(posts)} articles traités → {output_json_path}")
    return posts

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Colonnes du CSV source (export ContentFactory)
REQUIRED_COLUMNS = ['title', 'content_html', 'slug']
OPTIONAL_COLUMNS = ['metatitle', 'metadescription', 'keypoints', 'content_markdown']


def validate_csv(csv_path):
    """Vérifie que le CSV contient les colonnes attendues."""
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        print(f"[ERREUR] Colonnes manquantes dans {csv_path}: {', '.join(missing)}")
        print(f"  Colonnes trouvées: {', '.join(headers)}")
        sys.exit(1)

    present_opt = [c for c in OPTIONAL_COLUMNS if c in headers]
    absent_opt = [c for c in OPTIONAL_COLUMNS if c not in headers]
    print(f"[OK] Colonnes requises: {', '.join(REQUIRED_COLUMNS)}")
    if present_opt:
        print(f"[OK] Colonnes optionnelles: {', '.join(present_opt)}")
    if absent_opt:
        print(f"[INFO] Colonnes optionnelles absentes: {', '.join(absent_opt)}")
    return headers


def run_test():
    """Mode test avec un HTML de démonstration."""
    test_html = """<p>Introduction de l'article</p>

<div class="summary">
<h4>En bref :</h4>
<ul>
<li>Point clé 1</li>
<li>Point clé 2</li>
<li>Point clé 3</li>
</ul>
</div>

<h2>Section principale</h2>
<p>Contenu de la section...</p>

<table>
<tr><th>Licence</th><th>Type</th></tr>
<tr><td>Licence III</td><td>Vins et bières</td></tr>
<tr><td>Licence IV</td><td>Alcools forts</td></tr>
</table>

<div class="attention">
<h4>Information importante</h4>
<p>Ceci est une note d'information avec des détails importants.</p>
</div>

<div class="faq">
<h4>Peut-on ouvrir sans diplôme ?</h4>
<p>Oui, mais le permis d'exploitation est requis.</p>
<h4>Quel est le budget moyen ?</h4>
<p>Environ 150 000€ pour un bar standard.</p>
</div>"""

    result = parse_html_to_gutenberg(test_html)
    print("=" * 60)
    print("TEST PARSING HTML")
    print("=" * 60 + "\n")
    print(result)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convertit un CSV d'articles (content_html) en JSON WordPress avec blocs ACF."
    )
    parser.add_argument("csv_input", nargs="?", help="CSV source (colonnes: title, content_html, slug, ...)")
    parser.add_argument("-o", "--output", help="JSON de sortie (défaut: <input>_wp.json)")
    parser.add_argument("--csv-out", help="Exporter aussi un CSV safe (content tronqué)")
    parser.add_argument("--csv-full", help="Exporter aussi un CSV full (content complet)")
    parser.add_argument("--tags", nargs="*", type=int, default=[], help="IDs de tags WordPress")
    parser.add_argument("--test", action="store_true", help="Mode test (parsing HTML de démo)")
    parser.add_argument("--validate", action="store_true", help="Valider les colonnes du CSV sans convertir")

    args = parser.parse_args()

    if args.test:
        run_test()
        sys.exit(0)

    if not args.csv_input:
        parser.error("csv_input est requis (sauf avec --test)")

    if not os.path.exists(args.csv_input):
        print(f"[ERREUR] Fichier introuvable: {args.csv_input}")
        sys.exit(1)

    validate_csv(args.csv_input)

    if args.validate:
        sys.exit(0)

    base = os.path.splitext(args.csv_input)[0]
    output_json = args.output or f"{base}_wp.json"

    print(f"\nDémarrage: {args.csv_input} -> {output_json}\n")
    all_posts = process_csv(
        args.csv_input,
        output_json,
        tags=args.tags,
        output_csv_path=args.csv_out,
        output_csv_full_path=args.csv_full,
        output_csv_chunked_path=None,
    )

    print(f"\nPrêt pour l'import WordPress !")
