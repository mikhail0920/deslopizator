from dataclasses import dataclass

@dataclass(frozen=True)
class FunctionComplexity:
    path: str
    name: str
    line: int
    end_line: int
    complexity: int