from pathlib import Path
from lib import emit_json_error

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def load_template(type: str = "comprehensive") -> dict:
    name = {"comprehensive": "prd-comprehensive.md", "minimal": "prd-minimal.md"}.get(type)
    if not name:
        return emit_json_error(f"unknown template type: {type}", valid=["comprehensive", "minimal"])
    f = TEMPLATES_DIR / name
    if not f.exists():
        return emit_json_error(f"template file missing: {f}")
    return {"ok": True, "type": type, "content": f.read_text(), "path": str(f)}
