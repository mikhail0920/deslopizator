from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FileKind(Enum):
    PRODUCTION = "production"
    TEST = "test"
    GENERATED = "generated"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class SourceFile:
    path: str
    module: str | None
    kind: FileKind


@dataclass(frozen=True)
class ProjectConfig:
    source_roots: tuple[str, ...] = ("src",)
    exclude: tuple[str, ...] = ()
    generated: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectInventory:
    root: str
    files: tuple[SourceFile, ...]
    source_roots: tuple[str, ...]

    @property
    def production_files(self) -> tuple[SourceFile, ...]:
        return tuple(file for file in self.files if file.kind is FileKind.PRODUCTION)

    @property
    def test_files(self) -> tuple[SourceFile, ...]:
        return tuple(file for file in self.files if file.kind is FileKind.TEST)

    @property
    def generated_files(self) -> tuple[SourceFile, ...]:
        return tuple(file for file in self.files if file.kind is FileKind.GENERATED)

    @property
    def excluded_files(self) -> tuple[SourceFile, ...]:
        return tuple(file for file in self.files if file.kind is FileKind.EXCLUDED)

    def paths_for(self, kind: FileKind) -> tuple[Path, ...]:
        return tuple(Path(file.path) for file in self.files if file.kind is kind)
