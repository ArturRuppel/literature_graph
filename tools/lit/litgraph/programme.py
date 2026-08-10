"""Programme layer: emergent properties over aims, and the `lit programme` report.

The literature graph asks *what is known*. An aim asks *what would we have to do to know
it* — so the same slice primitive gains two kinds (Test, Capability) and two edges
(`discriminates`, `enabled_by`), and everything interesting is still read off the graph
rather than authored (programme design §8).

Nothing here is a field a curator writes. The three questions this module answers:

  1. **What am I quietly relying on?**  A claim with dependents, no test aimed at it, and no
     grounding in the literature is an *assumption* — ranked by how much collapses with it.
  2. **What can't I actually do?**  A test whose capability is claimed but not evidenced.
  3. **What is dead weight?**  Slices nothing points at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import (
    Aim,
    Graph,
    Slice,
    classify_ref,
    claim_is_borrowed,
    method_is_floor,
    reaches_floor,
)


def _global(container: str, ref: str) -> str:
    """A local ref → its global id; anything already global passes through."""
    return f"{container}:{ref}" if classify_ref(ref) == "local" else ref


def _is_programme(ref: str) -> bool:
    """Does this ref point into the programme (an aim) rather than the literature?"""
    return ref.startswith("@")


def _target_kind(ref: str) -> str:
    """The slice kind a local/sharpened ref names, read off its id prefix (SCHEMA §3).

    `b` (borrowed claim) and `oq` (open question) are the *same kinds* as `c` and `q` — the
    prefix records the curator's reading, not a kind — so they map together. `oq` is two
    characters and must be tested before the single-character lookup."""
    tail = ref.split(":", 1)[1] if ":" in ref else ref
    prefix = "oq" if tail.startswith("oq") else tail[:1]
    return {"c": "claim", "b": "claim", "q": "question", "oq": "question",
            "m": "method", "t": "test", "k": "capability"}.get(prefix, "")


# --- emergent properties ----------------------------------------------------


def _tested_claim_ids(aims: dict[str, Aim]) -> set[str]:
    """Global ids of claims some test is aimed at — either the test `discriminates` them,
    or they `grounded_in` the test directly (single-alternative grounding)."""
    out: set[str] = set()
    for aim in aims.values():
        for s in aim.slices:
            if s.kind == "test":
                for r in s.discriminates:
                    out.add(_global(aim.slug, r))
            elif s.kind == "claim":
                for r in s.grounded_in:
                    if _target_kind(r) == "test":
                        out.add(f"{aim.slug}:{s.id}")
    return out


def _dependents(aims: dict[str, Aim]) -> dict[str, set[str]]:
    """Reverse support map, global id → the slices that would break with it.

    `leads-to` is one edge in the ground→derived orientation, authored from either end
    (SCHEMA §5): `X.grounded_in ∋ Y` means X rests on Y, and `X.leads_to ∋ Z` means Z is
    derived from X. Both directions therefore feed the same reverse map."""
    rev: dict[str, set[str]] = {}
    for aim in aims.values():
        for s in aim.slices:
            me = f"{aim.slug}:{s.id}"
            for r in s.grounded_in:
                rev.setdefault(_global(aim.slug, r), set()).add(me)
            for r in s.leads_to:
                rev.setdefault(me, set()).add(_global(aim.slug, r))
    return rev


def _blast_radius(node: str, rev: dict[str, set[str]]) -> int:
    """Size of the transitive dependent closure — how much falls over if `node` is false."""
    seen: set[str] = set()
    stack = list(rev.get(node, ()))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(rev.get(n, ()))
    return len(seen)


def _modality(s: Slice, by_id: dict[str, Slice], rests_on_test: bool) -> str:
    """How would we come to believe this claim?

    *established* — it already rests on the literature, on our own data, or on an axiom.
    *proposed*    — a planned test would settle it. This is what a grant is asking for.
    *speculation* — neither. Load-bearing speculation is the thing to find.

    *proposed* dominates: a conjunction is only as established as its weakest link, so one
    planned experiment anywhere underneath makes the whole claim something the grant is
    asking for rather than reporting. Without that order, a hypothesis co-grounded in one
    citation reads as already known."""
    if rests_on_test:
        return "proposed"
    return "established" if _reaches_evidence(s, by_id) else "speculation"


def _rests_on_a_test(slug: str, s: Slice, by_id: dict[str, Slice], tested: set[str],
                     seen: set[str] | None = None) -> bool:
    """Does any part of this claim's support not exist yet? Walks `grounded_in` down through
    local claims; `tested` already carries the claims a test is aimed at directly."""
    seen = set() if seen is None else seen
    if s.id in seen:
        return False
    seen.add(s.id)
    if f"{slug}:{s.id}" in tested:
        return True
    for r in s.grounded_in:
        if classify_ref(r) != "local":
            continue
        t = by_id.get(r)
        if t is None:
            continue
        if t.kind == "test" or _rests_on_a_test(slug, t, by_id, tested, seen):
            return True
    return False


def _solid(by_id: dict[str, Slice]) -> dict[str, Slice]:
    """The id map with Tests removed, for walking a grounding chain downward.

    A Test is a *hollow* floor (design §2): it terminates the chain but marks it *proposed*,
    never *established*. Dropping tests from the map is what makes the walk stop at one —
    otherwise a claim resting on a planned experiment inherits that experiment's methods and
    their citations, and the central hypothesis of a grant reads as already known."""
    return {i: s for i, s in by_id.items() if s.kind != "test"}


def _reaches_evidence(s: Slice, by_id: dict[str, Slice], seen: set[str] | None = None) -> bool:
    """Walk `grounded_in` down: does this claim reach the literature, or a local floor?
    A ref into another aim is *not* evidence — the programme cannot ground itself.
    Callers pass a map without Tests (`_solid`), so the walk stops at a hollow floor."""
    seen = set() if seen is None else seen
    if s.id in seen:
        return False
    seen.add(s.id)
    if reaches_floor(s, by_id):
        return True
    for r in s.grounded_in:
        kind = classify_ref(r)
        if kind in ("container", "sharpened") and not _is_programme(r):
            return True                          # a citation into the literature
        if kind == "local":
            t = by_id.get(r)
            if t is not None and _reaches_evidence(t, by_id, seen):
                return True
    return False


def compute(g: Graph) -> None:
    """Fill every programme property on `g.aims`, in place. Assumes a validated graph."""
    tested = _tested_claim_ids(g.aims)
    rev = _dependents(g.aims)
    answered = _answered(g)

    # Capabilities and floors first — tests and claims read them.
    for aim in g.aims.values():
        for s in aim.slices:
            if s.kind == "method":
                s.is_floor = method_is_floor(s)
            elif s.kind == "claim" and s.floor_flag:
                s.is_floor = True
            elif s.kind == "capability":
                s.aspirational = not s.grounded_in

    for aim in g.aims.values():
        by_id = {s.id: s for s in aim.slices}
        solid = _solid(by_id)
        for s in aim.slices:
            me = f"{aim.slug}:{s.id}"
            deps = rev.get(me, set())
            if s.kind == "claim":
                s.borrowed = claim_is_borrowed(s)
                s.grounded = reaches_floor(s, solid)
                s.modality = _modality(s, solid, _rests_on_a_test(aim.slug, s, by_id, tested))
                s.blast_radius = _blast_radius(me, rev)
                # An assumption is something the work leans on that *nothing will ever check*.
                # A merely-proposed claim is checked, downstream of the test that settles its
                # support; flagging those too would drown the signal.
                s.load_bearing = (bool(deps) and me not in tested
                                  and s.modality == "speculation")
                # A rival hypothesis has no dependents by design — the test aimed at it is
                # what makes it live, so being discriminated counts as being pointed at.
                s.orphan = not deps and not s.answers and me not in tested
            elif s.kind == "question":
                s.answered = me in answered
            elif s.kind == "test":
                s.at_risk = any(_capability(r, by_id, g).aspirational
                                for r in s.enabled_by
                                if _capability(r, by_id, g) is not None)
                s.orphan = not s.discriminates and not deps
            elif s.kind == "capability":
                s.orphan = not _enabling_tests(me, g)
            s.color = _color(s)


def _answered(g: Graph) -> set[str]:
    from .graph import answered_question_ids
    return answered_question_ids(g.papers, g.aims)


def _capability(ref: str, by_id: dict[str, Slice], g: Graph) -> Slice | None:
    """Resolve an `enabled_by` ref to its Capability slice, local or cross-aim."""
    if classify_ref(ref) == "local":
        return by_id.get(ref)
    base, _, tid = ref.partition(":")
    aim = g.aims.get(base)
    if aim is None:
        return None
    return next((s for s in aim.slices if s.id == tid), None)


def _enabling_tests(cap_global: str, g: Graph) -> list[str]:
    """Global ids of the tests that name this capability in `enabled_by`."""
    out = []
    for aim in g.aims.values():
        for s in aim.slices:
            if s.kind == "test" and any(_global(aim.slug, r) == cap_global for r in s.enabled_by):
                out.append(f"{aim.slug}:{s.id}")
    return out


def _color(s: Slice) -> str:
    """Display color for a programme slice — modality for claims, state for the rest."""
    if s.kind == "claim":
        return s.modality or "speculation"
    if s.kind == "test":
        return "test-at-risk" if s.at_risk else "test"
    if s.kind == "capability":
        return "capability-aspirational" if s.aspirational else "capability"
    if s.kind == "question":
        return "question"
    return "floor" if s.is_floor else "model"


# --- the report -------------------------------------------------------------


@dataclass
class Finding:
    node: str
    text: str
    detail: str = ""


@dataclass
class Report:
    aims: int = 0
    slices: int = 0
    assumptions: list[Finding] = field(default_factory=list)   # load-bearing, by blast radius
    speculation: list[Finding] = field(default_factory=list)
    at_risk: list[Finding] = field(default_factory=list)
    aspirational: list[Finding] = field(default_factory=list)
    open_questions: list[Finding] = field(default_factory=list)
    orphans: list[Finding] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.assumptions or self.speculation or self.at_risk
                    or self.aspirational or self.orphans)


def _short(text: str, n: int = 88) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def report(g: Graph) -> Report:
    """Collect every §8 finding into a sorted, printable report."""
    r = Report(aims=len(g.aims))
    for aim in g.aims.values():
        by_id = {t.id: t for t in aim.slices}
        for s in aim.slices:
            r.slices += 1
            me = f"{aim.slug}:{s.id}"
            f = Finding(me, _short(s.text))
            if s.kind == "claim":
                if s.load_bearing:
                    f.detail = (f"{s.blast_radius} dependent"
                                f"{'s' if s.blast_radius != 1 else ''}, no test")
                    r.assumptions.append(f)
                elif s.modality == "speculation":
                    r.speculation.append(f)
                if s.orphan:
                    r.orphans.append(Finding(me, _short(s.text), "nothing depends on it"))
            elif s.kind == "question" and not s.answered:
                r.open_questions.append(f)
            elif s.kind == "test":
                if s.at_risk:
                    blocking = [r_ for r_ in s.enabled_by
                                if (c := _capability(r_, by_id, g)) is not None and c.aspirational]
                    r.at_risk.append(Finding(me, _short(s.text),
                                             "needs " + ", ".join(blocking)))
                if s.orphan:
                    r.orphans.append(Finding(me, _short(s.text), "discriminates nothing"))
            elif s.kind == "capability":
                if s.aspirational:
                    r.aspirational.append(Finding(me, _short(s.text), "no evidence it exists"))
                if s.orphan:
                    r.orphans.append(Finding(me, _short(s.text), "no test uses it"))

    r.assumptions.sort(key=lambda f: (-_radius_of(f.detail), f.node))
    for lst in (r.speculation, r.at_risk, r.aspirational, r.open_questions, r.orphans):
        lst.sort(key=lambda f: f.node)
    return r


def _radius_of(detail: str) -> int:
    try:
        return int(detail.split(" ", 1)[0])
    except (ValueError, IndexError):
        return 0


_SECTIONS = (
    ("assumptions", "load-bearing assumptions", "ranked by blast radius — what you rely on with no test"),
    ("speculation", "speculation", "no evidence, no test"),
    ("at_risk", "tests at risk", "a capability is claimed but not evidenced"),
    ("aspirational", "aspirational capabilities", ""),
    ("open_questions", "open questions", ""),
    ("orphans", "orphans", "nothing points at these"),
)


def format_report(r: Report) -> str:
    """The terminal rendering — every §8 payoff, no viewer required."""
    out = [f"=== lit programme ===",
           f"  {r.aims} aim{'s' if r.aims != 1 else ''}, {r.slices} slices"]
    for attr, heading, note in _SECTIONS:
        items = getattr(r, attr)
        if not items:
            continue
        out.append("")
        out.append(f"  {heading} ({len(items)})" + (f" — {note}" if note else ""))
        for f in items:
            tail = f"  [{f.detail}]" if f.detail else ""
            out.append(f"    {f.node}  {f.text}{tail}")
    if r.clean:
        out.append("")
        out.append("  nothing flagged.")
    return "\n".join(out) + "\n"
