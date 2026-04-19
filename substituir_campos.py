#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pymupdf>=1.24",
# ]
# ///
"""
Substitui placeholders {campo} em "Template Proposta.pdf" pelos valores
definidos em campos.json e gera "Proposta_Final.pdf".

A substituição é feita "de verdade": o texto original do placeholder é removido
do PDF (redação/redact) e o novo texto é desenhado no mesmo ponto, com a mesma
fonte, tamanho e cor — então o fundo original do template (gradiente) continua
visível, sem tarjas pretas.

Como rodar:

    # Recomendado (uv resolve e instala as dependências automaticamente):
    uv run substituir_campos.py

    # Ou, com pip:
    pip install pymupdf
    python3 substituir_campos.py

As fontes Montserrat-Bold e Montserrat-ExtraLight ficam em ./fonts/.
"""

from __future__ import annotations

import json
import os
import re
import sys

import pymupdf  # pymupdf >= 1.24 expõe `pymupdf`; versões antigas usavam `fitz`

# -------- Configurações --------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PDF = os.path.join(BASE_DIR, "Template Proposta.pdf")
CONFIG_JSON = os.path.join(BASE_DIR, "campos.json")
OUTPUT_PDF = os.path.join(BASE_DIR, "Proposta_Final.pdf")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

FONT_BOLD = os.path.join(FONTS_DIR, "Montserrat-bold.ttf")
FONT_EXTRALIGHT = os.path.join(FONTS_DIR, "Montserrat-extralight.ttf")
FONT_REGULAR = os.path.join(FONTS_DIR, "Montserrat-regular.ttf")

# Cores estritas do template (RGB 0..1)
COLOR_WHITE = (1.0, 1.0, 1.0)
COLOR_PEACH = (1.0, 0xAA / 255, 0x78 / 255)

# Métricas da Montserrat (ascent=968, descent=-251 por 1000 unidades)
DESCENT_RATIO = 0.251
ASCENT_RATIO = 0.968

# Padrão de placeholder: {nome}
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_\-]+)\}")


# --------------------------------------------------------------------------
def choose_font(original_font_name: str) -> tuple[str, str]:
    """Dado o nome da fonte original (da span do pymupdf), decide qual arquivo
    Montserrat usar — sempre dentro da família Montserrat (branco/pêssego).

    Retorna (fontname_alias, fontfile_path).
    """
    name = (original_font_name or "").lower()
    if "extralight" in name or "ultralight" in name:
        return "MtsExtraLight", FONT_EXTRALIGHT
    if "bold" in name or "black" in name or "extrabold" in name:
        return "MtsBold", FONT_BOLD
    return "MtsRegular", FONT_REGULAR


def find_placeholders(doc: "pymupdf.Document"):
    """Varre todas as páginas e localiza cada span que contém um {placeholder}.
    Retorna uma lista de dicts com tudo o que é necessário para redigir e
    reescrever o campo.
    """
    placeholders = []
    for page_idx, page in enumerate(doc):
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:  # só blocos de texto
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    m = PLACEHOLDER_RE.search(text)
                    if not m:
                        continue
                    placeholders.append({
                        "page": page_idx,
                        "name": m.group(1),
                        "raw_text": text,
                        "bbox": pymupdf.Rect(span["bbox"]),
                        "font_name": span.get("font", ""),
                        "size": float(span.get("size", 24)),
                        "page_rect": page.rect,
                    })
    return placeholders


def wrap_text(text: str, font: pymupdf.Font, size: float, max_width: float):
    """Quebra texto em linhas que caibam em max_width usando métricas da fonte."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        tentative = (current + " " + word).strip()
        w = font.text_length(tentative, size)
        if w <= max_width or not current:
            current = tentative
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def insert_replacement(page: "pymupdf.Page", ph: dict, value: str):
    """Desenha o texto substituto na página (assume que o placeholder já foi
    redigido/removido antes)."""

    font_alias, font_file = choose_font(ph["font_name"])
    size = ph["size"]
    is_big_quote = ("bold" in ph["font_name"].lower() and size > 40)
    is_bullet_list = ph["name"].lower() == "lista"
    # Frases em página inteira (metodo, conclusao) — precisam de wrap sem mesclar cores.
    is_paragraph = ph["name"].lower() in {"metodo", "conclusao"}

    # baseline em coordenadas do pymupdf (origem no topo)
    bbox = ph["bbox"]
    baseline_y = bbox.y1 - DESCENT_RATIO * size
    x0 = bbox.x0

    page.insert_font(fontname=font_alias, fontfile=font_file)

    if is_big_quote:
        # Citação grande: alterna palavras em branco e pêssego, quebrando em
        # múltiplas linhas se necessário.
        font = pymupdf.Font(fontfile=font_file)
        margin_right = 30
        max_width = ph["page_rect"].width - x0 - margin_right

        working_size = size
        while working_size >= 28:
            lines = wrap_text(value, font, working_size, max_width)
            if len(lines) <= 5:
                break
            working_size -= 2
        else:
            lines = wrap_text(value, font, working_size, max_width)

        line_height = working_size * 1.15
        space_w = font.text_length(" ", working_size)

        word_idx = 0
        for li, line in enumerate(lines):
            x = x0
            y = baseline_y + li * line_height
            for word in line.split(" "):
                color = COLOR_WHITE if word_idx % 2 == 0 else COLOR_PEACH
                page.insert_text(
                    (x, y), word,
                    fontname=font_alias, fontsize=working_size, color=color,
                )
                x += font.text_length(word, working_size) + space_w
                word_idx += 1
    elif is_bullet_list:
        # Lista de bullets: o valor contém um item por linha (separados por \n).
        # O template já desenha o bullet do primeiro item como vetor —
        # para os demais itens desenhamos um bullet igual (círculo branco).
        items = [ln.strip() for ln in value.splitlines() if ln.strip()]
        if not items:
            return

        font = pymupdf.Font(fontfile=font_file)
        margin_right = 40
        max_width = ph["page_rect"].width - x0 - margin_right
        line_height = size * 1.45

        # Bullet original do template: pequeno círculo preenchido.
        # No template inspecionado: rect=(91.12, 323.55, 97.12, 329.55) ≈ diâmetro 6pt.
        bullet_radius = 3.0
        bullet_cx = x0 - 13.0  # ~13pt à esquerda do texto (igual ao template)
        # y-center do primeiro bullet corresponde ao centro da linha do texto original
        first_bullet_cy = (bbox.y0 + bbox.y1) / 2

        current_y = baseline_y
        for idx, item in enumerate(items):
            sub_lines = wrap_text(item, font, size, max_width)
            for li, sub in enumerate(sub_lines):
                page.insert_text(
                    (x0, current_y), sub,
                    fontname=font_alias, fontsize=size, color=COLOR_WHITE,
                )
                if li == 0 and idx > 0:
                    # Desenha bullet para os itens 2..N (o item 1 reaproveita o
                    # bullet vetorial original que sobreviveu à redação).
                    bullet_cy = first_bullet_cy + (current_y - baseline_y)
                    page.draw_circle(
                        (bullet_cx, bullet_cy),
                        radius=bullet_radius,
                        color=COLOR_WHITE, fill=COLOR_WHITE,
                    )
                current_y += line_height
    elif is_paragraph:
        # Frase corrida — suporta wrap mas sem alternar cores.
        font = pymupdf.Font(fontfile=font_file)
        margin_right = 40
        max_width = ph["page_rect"].width - x0 - margin_right
        lines = wrap_text(value, font, size, max_width)
        line_height = size * 1.35
        for li, line in enumerate(lines):
            y = baseline_y + li * line_height
            page.insert_text(
                (x0, y), line,
                fontname=font_alias, fontsize=size, color=COLOR_WHITE,
            )
    else:
        # Campo inline: preserva o prefixo (espaços iniciais antes do `{`) e o
        # sufixo (ex.: ";") — ambos foram apagados junto na redação.
        prefix_match = re.match(r"^(\s*)\{", ph["raw_text"])
        prefix = prefix_match.group(1) if prefix_match else ""
        suffix_match = re.search(r"\}([^\w]*)$", ph["raw_text"])
        suffix = suffix_match.group(1) if suffix_match else ""
        page.insert_text(
            (x0, baseline_y), f"{prefix}{value}{suffix}",
            fontname=font_alias, fontsize=size, color=COLOR_WHITE,
        )


def generate_pdf(values: dict, template_path: str = TEMPLATE_PDF, verbose: bool = False) -> bytes:
    """Gera o PDF substituindo placeholders pelos valores informados e devolve
    os bytes do PDF resultante (sem gravar em disco)."""
    doc = pymupdf.open(template_path)

    placeholders = find_placeholders(doc)
    if verbose:
        print(f"Placeholders encontrados: {[p['name'] for p in placeholders]}")

    # Agrupa por página
    by_page: dict[int, list] = {}
    for p in placeholders:
        by_page.setdefault(p["page"], []).append(p)

    # 1) Redige (remove fisicamente) todos os placeholders que serão trocados.
    for page_idx, items in by_page.items():
        page = doc[page_idx]
        something_to_redact = False
        for ph in items:
            if values.get(ph["name"], "") == "":
                if verbose:
                    print(f"  [aviso] campo {{{ph['name']}}} vazio — mantendo placeholder")
                continue
            rects = page.search_for(ph["raw_text"])
            if not rects:
                rects = [ph["bbox"]]
            for r in rects:
                page.add_redact_annot(r, fill=None)
            something_to_redact = True
        if something_to_redact:
            # images=0, graphics=0 preserva o fundo (gradiente) por baixo
            page.apply_redactions(images=0, graphics=0)

    # 2) Insere o novo texto
    for page_idx, items in by_page.items():
        page = doc[page_idx]
        for ph in items:
            value = values.get(ph["name"], "")
            if value == "":
                continue
            insert_replacement(page, ph, str(value))

    # garbage=1 + deflate=False deixam o arquivo maior mas reduzem
    # drasticamente o pico de memória (importante em hosts com 512 MB).
    pdf_bytes = doc.tobytes(garbage=1, deflate=False)
    doc.close()
    return pdf_bytes


def main():
    if not os.path.exists(TEMPLATE_PDF):
        sys.exit(f"Template não encontrado: {TEMPLATE_PDF}")
    if not os.path.exists(CONFIG_JSON):
        sys.exit(
            f"campos.json não encontrado: {CONFIG_JSON}\n"
            f"Preencha-o antes de rodar o script "
            f"(abra formulario.html e clique em 'Baixar campos.json')."
        )

    with open(CONFIG_JSON, encoding="utf-8") as f:
        values = json.load(f)

    pdf_bytes = generate_pdf(values, verbose=True)

    with open(OUTPUT_PDF, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF gerado: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
