#!/usr/bin/env python
"""
Build the printable product catalog (PDF) from the seed catalog definitions.

Usage:  python scripts/build_catalog_pdf.py [output.pdf]

The product list, descriptions and prices are read straight from
``core.management.commands.seed_data.Command`` so the PDF can never drift from
what ``python manage.py seed_data`` loads into the store. Product photos are
taken from ``fixtures/product_images/<SKU>.jpg``; a neutral placeholder is
rendered for any product whose photo is missing.
"""
from __future__ import annotations

import io
import os
import sys
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')

import django  # noqa: E402

django.setup()

from django.utils.text import slugify  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

from core.management.commands.seed_data import FIXTURE_IMAGE_DIR, Command  # noqa: E402

STORE_NAME = 'StarEast Store'
ACCENT = colors.HexColor('#4F46E5')
INK = colors.HexColor('#111827')
MUTED = colors.HexColor('#6B7280')
LIGHT = colors.HexColor('#F3F4F6')
SALE = colors.HexColor('#DC2626')

styles = getSampleStyleSheet()
TITLE = ParagraphStyle('title', parent=styles['Title'], fontSize=34, leading=40,
                       textColor=INK, alignment=TA_CENTER, spaceAfter=6)
SUBTITLE = ParagraphStyle('subtitle', parent=styles['Normal'], fontSize=13,
                          leading=18, textColor=MUTED, alignment=TA_CENTER)
CATEGORY = ParagraphStyle('category', parent=styles['Heading1'], fontSize=22,
                          leading=26, textColor=ACCENT, spaceBefore=0, spaceAfter=2)
CATEGORY_DESC = ParagraphStyle('category_desc', parent=styles['Normal'],
                               fontSize=10.5, textColor=MUTED, spaceAfter=10)
NAME = ParagraphStyle('name', parent=styles['Heading4'], fontSize=12,
                      leading=15, textColor=INK, spaceBefore=0, spaceAfter=2)
SKU = ParagraphStyle('sku', parent=styles['Normal'], fontSize=8, textColor=MUTED,
                     spaceAfter=4)
DESC = ParagraphStyle('desc', parent=styles['Normal'], fontSize=9.5, leading=13,
                      textColor=INK)
PRICE = ParagraphStyle('price', parent=styles['Normal'], fontSize=13, leading=16,
                       textColor=INK, spaceBefore=6)
FOOT = ParagraphStyle('foot', parent=styles['Normal'], fontSize=8, textColor=MUTED,
                      alignment=TA_CENTER)


def sku_for(category_name: str, position: int) -> str:
    return f'SE-{slugify(category_name).upper()[:4]}-{position + 1:03d}'


def image_path(sku: str) -> Path | None:
    for extension in ('jpg', 'jpeg', 'png', 'webp'):
        candidate = Path(FIXTURE_IMAGE_DIR) / f'{sku}.{extension}'
        if candidate.exists():
            return candidate
    return None


def placeholder(name: str, size: int = 600) -> io.BytesIO:
    """Soft grey tile with the product initials, used until a photo exists."""
    tile = Image.new('RGB', (size, size), (243, 244, 246))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle([20, 20, size - 20, size - 20], radius=40,
                           outline=(209, 213, 219), width=4)
    initials = ''.join(word[0] for word in name.split()[:2]).upper()
    try:
        draw.text((size / 2, size / 2 - 20), initials, anchor='mm',
                  fill=(156, 163, 175), font_size=150)
        draw.text((size / 2, size / 2 + 110), 'photo coming soon', anchor='mm',
                  fill=(156, 163, 175), font_size=30)
    except (TypeError, OSError):
        draw.text((size / 2 - 30, size / 2), initials, fill=(156, 163, 175))
    buffer = io.BytesIO()
    tile.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return buffer


def product_image(sku: str, name: str, side: float) -> RLImage:
    path = image_path(sku)
    source = str(path) if path else placeholder(name)
    image = RLImage(source, width=side, height=side)
    image.hAlign = 'CENTER'
    return image


def price_markup(price: str, sale_price: str | None) -> str:
    if sale_price:
        percent = round((1 - Decimal(sale_price) / Decimal(price)) * 100)
        return (
            f'<font color="{SALE.hexval()}"><b>${Decimal(sale_price):,.2f}</b></font> '
            f'&nbsp;<font size="9" color="{MUTED.hexval()}"><strike>${Decimal(price):,.2f}</strike>'
            f' &nbsp;Save {percent}%</font>'
        )
    return f'<b>${Decimal(price):,.2f}</b>'


def product_card(sku: str, name: str, description: str, price: str,
                 sale_price: str | None, side: float) -> Table:
    body = [
        Paragraph(name, NAME),
        Paragraph(f'SKU {sku}', SKU),
        Paragraph(description, DESC),
        Paragraph(price_markup(price, sale_price), PRICE),
    ]
    card = Table([[product_image(sku, name, side)], [body]],
                 colWidths=[side + 8 * mm])
    card.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#E5E7EB')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, 0), 4 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2 * mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 4 * mm),
    ]))
    return card


def draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(A4[0] / 2, 12 * mm,
                             f'{STORE_NAME} - Product Catalog - Page {doc.page}')
    canvas.restoreState()


def build(output: Path) -> int:
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, title=f'{STORE_NAME} Product Catalog',
        author=STORE_NAME, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=20 * mm,
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin
    gutter = 6 * mm
    column = (content_width - gutter) / 2
    side = column - 8 * mm - 12 * mm  # leave room for two rows + heading per page

    categories = dict(Command.CATEGORIES)
    products = Command.PRODUCTS
    total = sum(len(items) for items in products.values())

    story = [
        Spacer(1, 60 * mm),
        Paragraph(STORE_NAME, TITLE),
        Paragraph('Product Catalog', SUBTITLE),
        Spacer(1, 6 * mm),
        Paragraph(f'{total} products across {len(products)} categories', SUBTITLE),
        Spacer(1, 90 * mm),
        Paragraph('Prices in USD. Sale prices shown in red with the regular price struck through.',
                  FOOT),
        PageBreak(),
    ]

    for category_name, items in products.items():
        heading = [Paragraph(category_name, CATEGORY),
                   Paragraph(categories.get(category_name, ''), CATEGORY_DESC)]
        cards = [
            product_card(sku_for(category_name, position), name, description,
                         price, sale_price, side)
            for position, (name, description, price, sale_price) in enumerate(items)
        ]
        rows = [cards[i:i + 2] for i in range(0, len(cards), 2)]
        for row in rows:
            if len(row) == 1:
                row.append('')
        grid = Table(rows, colWidths=[column, column], hAlign='LEFT')
        grid.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), gutter),
            ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), gutter),
        ]))
        story.append(KeepTogether(heading + [grid]))
        story.append(PageBreak())

    if isinstance(story[-1], PageBreak):
        story.pop()
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return total


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / 'docs' / 'StarEastStore_Product_Catalog.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    count = build(target)
    print(f'Wrote {count} products to {target}')
