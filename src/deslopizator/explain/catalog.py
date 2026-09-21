from dataclasses import dataclass


@dataclass(frozen=True)
class RuleExplanation:
    code: str
    slug: str
    title: str
    what: str
    detection: str
    why: str
    false_positives: str
    when_ok: str
    questions: tuple[str, ...]
    clear_condition: str


RULES = (
    RuleExplanation(
        "DS101", "pass-through", "pass-through-function",
        "A function forwards its arguments directly to another call.",
        "One meaningful return statement is a call whose arguments correspond 1:1 to the function parameters.",
        "This layer currently adds no observable behaviour.",
        "An intentional API boundary, compatibility wrapper, or instrumentation hook can look the same.",
        "When the wrapper is a deliberate public boundary or a seam for future behaviour.",
        ("Is this an intentional API boundary?", "Is behaviour expected to appear here?", "Could callers depend on the lower-level API directly?"),
        "The function contains only a direct forwarding return and is not an exempt protocol/property/dunder method.",
    ),
    RuleExplanation(
        "DS102", "delegating-class", "delegating-class",
        "A public class API mostly forwards calls to one object.",
        "At least three public methods are present, at least 80% are pass-throughs, and they target one attribute.",
        "The observed public methods currently add no behaviour before delegating to the same object.",
        "A stable facade, dependency boundary, or intentionally narrow API can be useful.",
        "When the facade protects callers from a lower-level API or is expected to gain behaviour.",
        ("Is this facade part of a deliberate public contract?", "Would exposing the target couple callers to implementation details?"),
        "Three or more public methods mostly forward to the same object.",
    ),
    RuleExplanation(
        "DS103", "delegation-chain", "delegation-chain",
        "Several statically resolvable functions forward the same call through a chain.",
        "A chain of at least three pass-through functions is resolved from local class assignments and unique method targets.",
        "Intermediate layers currently add no behaviour.",
        "Layered APIs and seams can intentionally preserve a stable call path.",
        "When each layer owns a meaningful contract even if its current body is small.",
        ("Which layer should own the behaviour?", "Are the intermediate APIs stable contracts?"),
        "A statically resolvable chain has at least three behaviour-free forwarding functions.",
    ),
    RuleExplanation(
        "DS104", "single-implementation-abstraction", "single-implementation-abstraction",
        "An ABC or Protocol has one known in-project implementation.",
        "An abstract class or Protocol is matched to one explicit subclass in the discovered production files.",
        "The repository currently contains one explicit implementation of this abstraction.",
        "A single implementation can still be a boundary for tests, plugins, or future implementations.",
        "When the abstraction is an intentional extension or dependency-injection boundary.",
        ("Is another implementation expected outside this repository?", "Does the abstraction improve testing or ownership?"),
        "An explicit ABC/Protocol has exactly one known subclass.",
    ),
    RuleExplanation(
        "DS105", "swallowed-exception", "swallowed-exception",
        "A broad exception is discarded or replaced with a constant fallback.",
        "A bare, Exception, or BaseException handler has only pass, continue, break, or a constant return.",
        "The failure is hidden from callers and may make diagnosis or correctness harder.",
        "Best-effort cleanup and intentionally tolerant parsing can require a fallback.",
        "When the fallback is documented and the lost exception is intentionally irrelevant.",
        ("Should this exception be logged or re-raised?", "Is the fallback part of the API contract?"),
        "A broad handler has no action beyond swallowing or returning a constant fallback.",
    ),
)


def rule_for(value: str) -> RuleExplanation | None:
    normalized = value.lower()
    return next((rule for rule in RULES if normalized in {rule.code.lower(), rule.slug, rule.title}), None)
