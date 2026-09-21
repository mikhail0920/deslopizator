from math import log

from deslopizator.scoring.models import DimensionParameters, DimensionScore


def density_burden(value: float, saturation: float) -> float:
    if saturation <= 0:
        raise ValueError("saturation must be positive")
    return min(1.0, value / saturation)


def count_burden(count: int, scale: float) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return log(1 + count / scale) / (1 + log(1 + count / scale))


def dimension_score(raw_density: float, raw_count: int, parameters: DimensionParameters) -> DimensionScore:
    density = density_burden(raw_density, parameters.density_saturation)
    count = count_burden(raw_count, parameters.count_scale)
    return DimensionScore(
        raw_density=raw_density,
        raw_count=raw_count,
        density_burden=density,
        count_burden=count,
        score=0.5 * density + 0.5 * count,
    )
