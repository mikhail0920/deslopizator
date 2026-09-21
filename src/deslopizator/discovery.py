from pathlib import Path

from deslopizator.inventory.classifier import discover_project

def discover_code_files(path: str) -> list[Path]:
    dir = Path(path)

    if dir.is_file():
        if dir.suffix == '.py':
            return [dir]
        return []

    ignore_set = {'.git', '.venv', 'venv', '__pycache__'}

    return sorted([
        p for p in dir.rglob('*.py') if not any(part in ignore_set for part in p.parts)
    ])


def discover_inventory(path: str | Path):
    return discover_project(path)
