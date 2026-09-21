import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deslopizator.audit import analyze_project
from deslopizator.history.git import collect_file_churn
from deslopizator.history.hotspots import build_hotspots
from deslopizator.history.models import FileChurn, FileStructuralDebt
from deslopizator.inventory.classifier import discover_project


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True)


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "app.py")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        message,
    )


def test_git_churn_collects_windows_authors_and_numstat(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _commit(tmp_path, "initial")
    path.write_text("value = 2\nextra = 3\n", encoding="utf-8")
    _commit(tmp_path, "change")

    result = collect_file_churn(tmp_path, [path], now=datetime.now(timezone.utc) + timedelta(minutes=1))

    assert result[0] == FileChurn(str(path.resolve()), 2, 2, 2, 1, 3, 1)


def test_high_debt_and_high_churn_have_high_priority():
    debt = (
        FileStructuralDebt("a.py", 10.0, 2, 0, 0, False, 0.8),
        FileStructuralDebt("b.py", 2.0, 0, 0, 0, False, 0.2),
    )
    churn = (
        FileChurn("a.py", 0, 20, 20, 1, 0, 0),
        FileChurn("b.py", 0, 1, 1, 1, 0, 0),
    )

    result = build_hotspots(debt, churn)

    assert result[0].path == "a.py"
    assert result[0].priority == 1.0


def test_high_debt_and_zero_churn_have_zero_priority():
    debt = (FileStructuralDebt("a.py", 10.0, 1, 0, 0, False, 0.8),)
    churn = (FileChurn("a.py", 0, 0, 0, 0, 0, 0),)

    assert build_hotspots(debt, churn)[0].priority == 0


def test_high_churn_and_zero_debt_have_zero_priority():
    debt = (FileStructuralDebt("a.py", 0.0, 0, 0, 0, False, 0.0),)
    churn = (FileChurn("a.py", 0, 20, 20, 1, 0, 0),)

    assert build_hotspots(debt, churn)[0].priority == 0


def test_git_unavailability_does_not_break_audit(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")

    result = analyze_project(tmp_path)

    assert result.git_available is False
    assert result.churn[0].commits_180d == 0
    assert result.hotspots[0].priority == 0
    assert result.coupling_available is False
    assert result.coupling == ()


def test_hotspots_have_deterministic_ordering():
    debt = (
        FileStructuralDebt("z.py", 1.0, 1, 0, 0, False, 0.5),
        FileStructuralDebt("a.py", 1.0, 1, 0, 0, False, 0.5),
    )
    churn = (
        FileChurn("z.py", 0, 3, 3, 1, 0, 0),
        FileChurn("a.py", 0, 3, 3, 1, 0, 0),
    )

    assert [item.path for item in build_hotspots(debt, churn)] == ["a.py", "z.py"]
