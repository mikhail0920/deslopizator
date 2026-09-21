from deslopizator.explain.catalog import RuleExplanation, rule_for


def render_rule(rule: RuleExplanation) -> str:
    lines = [f"{rule.code} {rule.title}", "", f"WHAT\n  {rule.what}", f"\nDETECTION\n  {rule.detection}", f"\nWHY\n  {rule.why}", f"\nFALSE POSITIVES\n  {rule.false_positives}", f"\nWHEN IT IS OK\n  {rule.when_ok}", "\nQUESTIONS TO ASK"]
    lines.extend(f"  {question}" for question in rule.questions)
    lines.extend((f"\nCLEAR CONDITION\n  {rule.clear_condition}", f"\nConfidence levels: certain, high, medium."))
    return "\n".join(lines)


def render_explanation(value: str) -> str:
    rule = rule_for(value)
    if rule is None:
        raise KeyError(value)
    return render_rule(rule)
