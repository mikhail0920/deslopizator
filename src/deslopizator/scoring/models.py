from dataclasses import dataclass

from deslopizator.scoring.version import SCORING_VERSION


@dataclass(frozen=True)
class DimensionParameters:
    density_saturation: float
    count_scale: float


@dataclass(frozen=True)
class ScoringParameters:
    complexity_density_saturation: float = 0.25
    complexity_count_scale: float = 20.0
    duplication_density_saturation: float = 0.15
    duplication_count_scale: float = 15.0
    cycles_density_saturation: float = 0.10
    cycles_count_scale: float = 5.0
    complexity_weight: float = 0.50
    duplication_weight: float = 0.30
    cycles_weight: float = 0.20

    @property
    def complexity(self) -> DimensionParameters:
        return DimensionParameters(self.complexity_density_saturation, self.complexity_count_scale)

    @property
    def duplication(self) -> DimensionParameters:
        return DimensionParameters(self.duplication_density_saturation, self.duplication_count_scale)

    @property
    def cycles(self) -> DimensionParameters:
        return DimensionParameters(self.cycles_density_saturation, self.cycles_count_scale)


@dataclass(frozen=True)
class DimensionScore:
    raw_density: float
    raw_count: int
    density_burden: float
    count_burden: float
    score: float


@dataclass(frozen=True)
class SlopScore:
    version: str
    total: float | None
    complexity: DimensionScore | None
    duplication: DimensionScore | None
    cycles: DimensionScore | None
    partial: bool
