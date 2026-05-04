# WP_KEO_ACF

Pipeline de conversion de contenu Keobiz (CSV) vers des articles WordPress avec blocs ACF (Advanced Custom Fields).

## Ce que fait le projet

Transforme des exports CSV d'articles en JSON WordPress prêt pour l'import via **WP All Import**, avec génération automatique des blocs ACF Gutenberg :

| Bloc source (HTML) | Bloc WordPress généré |
|---|---|
| `<ol>/<ul>` keypoints | `acf/summary` |
| `<div class="note/advice/attention">` | `acf/information` |
| `<table>` | `acf/tableau` |
| H3/H4 avec "?" groupés en fin d'article | `acf/faq-post-new` |
| Liens sources | `acf/sources` |
| HTML standard | `wp:html` |

## Colonnes CSV attendues

**Requises :** `title`, `content_html`, `slug`

**Optionnelles :** `metatitle`, `metadescription`, `keypoints`, `content_markdown`

## Structure

```
csv_to_wordpress.py    # Script principal - CSV -> JSON WordPress ACF
scan_faq_from_csv.py   # Audit - scanne les FAQ dans un CSV
verify_csv_content.py  # Verification - controle l'integrite du contenu CSV
csv_inputs/            # Deposer les CSV sources ici
```

## Utilisation

### Conversion CSV -> WordPress

```bash
# Conversion standard
python csv_to_wordpress.py csv_inputs/mon_batch.csv

# Specifier le JSON de sortie
python csv_to_wordpress.py csv_inputs/mon_batch.csv -o output.json

# Exporter aussi des CSV de controle
python csv_to_wordpress.py csv_inputs/mon_batch.csv --csv-out safe.csv --csv-full full.csv

# Ajouter des tags WordPress
python csv_to_wordpress.py csv_inputs/mon_batch.csv --tags 12 45

# Valider les colonnes sans convertir
python csv_to_wordpress.py csv_inputs/mon_batch.csv --validate

# Mode test (parsing HTML de demo)
python csv_to_wordpress.py --test
```

### Audit FAQ

```bash
# Scanner les FAQ dans un CSV
python scan_faq_from_csv.py mon_export.csv

# Specifier le fichier de sortie
python scan_faq_from_csv.py mon_export.csv -o rapport.csv
```

### Verification contenu

```bash
# Resume global du CSV
python verify_csv_content.py csv_inputs/mon_batch.csv

# Chercher des articles par titre
python verify_csv_content.py csv_inputs/mon_batch.csv "Mon article" "Autre article"
```

## Prerequis

```bash
pip install beautifulsoup4
```

## Configuration ACF

Les field keys ACF sont definies en haut de `csv_to_wordpress.py` dans le dictionnaire `ACF_MAP`. A adapter si les champs ACF changent cote WordPress.
