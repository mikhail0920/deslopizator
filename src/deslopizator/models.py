from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class FunctionMetrics:
    path: str
    name: str
    qualified_name: str
    line: int
    end_line: int
    complexity: int
    sloc: int
    max_nesting: int
    statement_count: int
    parameter_count: int
    return_count: int

    @property
    def mass(self) -> float:
        return self.complexity * sqrt(self.sloc)

    @property
    def eroded(self) -> bool:
        return self.complexity > 10


FunctionComplexity = FunctionMetrics


@dataclass(frozen=True)
class FileComplexityMetrics:
    path: str
    functions: tuple[FunctionMetrics, ...]
    total_function_mass: float
    eroded_function_mass: float
    eroded_function_count: int

    @property
    def eroded_mass_share(self) -> float:
        if self.total_function_mass == 0:
            return 0.0
        return self.eroded_function_mass / self.total_function_mass
