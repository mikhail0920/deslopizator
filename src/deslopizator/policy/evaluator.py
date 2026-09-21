from deslopizator.completeness.models import AnalysisStatus, AuditResult
from deslopizator.policy.config import PolicyConfig
from deslopizator.policy.models import AuditDiff, PolicyResult, PolicyViolation

def _violation(rule: str, expected: str, actual: str, message: str) -> PolicyViolation:
    return PolicyViolation(rule, expected, actual, message)

def _partial_violations(result: AuditResult, config: PolicyConfig) -> list[PolicyViolation]:
    if config.allow_partial:
        return []
    violations = []
    for name, dimension in (("complexity", result.completeness.complexity), ("duplication", result.completeness.duplication), ("imports", result.completeness.imports)):
        if dimension.status is AnalysisStatus.PARTIAL:
            reason = "; ".join(dimension.reasons) or "incomplete analysis"
            violations.append(_violation("analysis-completeness", "complete", dimension.status.value, f"{name}: {reason}"))
    return violations

def evaluate(result: AuditResult, config: PolicyConfig) -> PolicyResult:
    violations = _partial_violations(result, config)
    architecture = getattr(result, "architecture", None)
    architecture_count = architecture.violation_count if architecture is not None else 0
    if architecture_count > config.max_architecture_violations:
        violations.append(_violation(
            "max-architecture-violations",
            str(config.max_architecture_violations),
            str(architecture_count),
            "architecture violations exceed budget",
        ))
    if config.max_score is not None and result.score.total is not None and result.score.total > config.max_score:
        violations.append(_violation("max-score", f"<= {config.max_score:g}", f"{result.score.total:.1f}", "score exceeds maximum"))
    return PolicyResult(not violations, tuple(violations))

def evaluate_diff(diff: AuditDiff, config: PolicyConfig) -> PolicyResult:
    violations = _partial_violations(diff.baseline, config) + _partial_violations(diff.current, config)
    if diff.baseline.score.version != diff.current.score.version:
        violations.append(_violation("scoring-version", diff.baseline.score.version, diff.current.score.version, "incompatible scoring versions"))
    if diff.current.score.total is not None and diff.score_increase > config.max_score_increase:
        violations.append(_violation("max-score-increase", f"<= {config.max_score_increase:g}", f"+{diff.score_increase:.1f}", "score increased beyond budget"))
    if diff.new_eroded_functions > config.max_new_eroded_functions:
        violations.append(_violation("max-new-eroded-functions", str(config.max_new_eroded_functions), str(diff.new_eroded_functions), "new eroded functions exceed budget"))
    if diff.density_increase > config.max_density_increase:
        violations.append(_violation("max-density-increase", f"<= {config.max_density_increase:g}", f"+{diff.density_increase:.3f}", "duplication density increased beyond budget"))
    if diff.new_clone_groups > config.max_new_clone_groups:
        violations.append(_violation("max-new-clone-groups", str(config.max_new_clone_groups), str(diff.new_clone_groups), "new clone groups exceed budget"))
    if diff.new_cycle_groups > config.max_new_cycle_groups:
        violations.append(_violation("max-new-cycle-groups", str(config.max_new_cycle_groups), str(diff.new_cycle_groups), "new cycle groups exceed budget"))
    if diff.new_architecture_violations > config.max_new_architecture_violations:
        violations.append(_violation(
            "max-new-architecture-violations",
            str(config.max_new_architecture_violations),
            str(diff.new_architecture_violations),
            "new architecture violations exceed budget",
        ))
    return PolicyResult(not violations, tuple(violations))
