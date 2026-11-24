"""Rebuilds app/label.html from app/label_template.html and data/items.json.

Usage: python scripts/build_app.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
items = json.load(open(ROOT / "data" / "items.json"))
html = (ROOT / "app" / "label_template.html").read_text()
(ROOT / "app" / "label.html").write_text(html.replace("__ITEMS__", json.dumps(items).replace("</", "<\\/")))
print(f"app/label.html built with {len(items)} conversations")
