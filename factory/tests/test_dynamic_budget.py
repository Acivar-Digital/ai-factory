"""Tests for DynamicBudget -- line-count-aware tool allocation.

Verifies four invariants:
  1. write_budget = max(35, line_count // 2)
  2. read_budget  = 2 * write_budget
  3. Soft nudge fires at the 80 % threshold (non-blocking warning)
  4. Circuit breaker hard-halts at 100 % (blocking force-stop)

Self-contained: stdlib only, no external packages required.
"""


class DynamicBudget:
    """Line-count-aware budget tracker for tool-call allocation.

    ``write_budget = max(35, line_count // 2)``
    ``read_budget  = 2 * write_budget``

    A soft nudge warns when usage reaches 80 % of a budget.  A circuit
    breaker force-halts when usage reaches 100 %.  The nudge never
    suppresses the hard stop -- both thresholds fire independently.
    """

    SOFT_NUDGE_FRACTION: float = 0.80
    HARD_HALT_FRACTION: float = 1.00
    MIN_WRITE_BUDGET: int = 35
    SOFT_NUDGE_MSG: str = (
        "SOFT_NUDGE: budget at 80 %. Begin finalizing output."
    )
    HALT_MSG: str = (
        "HALT: Circuit breaker tripped - budget exhausted at 100 %. "
        "Emit final_result now."
    )

    def __init__(self, line_count: int) -> None:
        self.line_count: int = line_count
        self.write_budget: int = max(self.MIN_WRITE_BUDGET, line_count // 2)
        self.read_budget: int = 2 * self.write_budget
        self.writes_used: int = 0
        self.reads_used: int = 0
        self.soft_nudged: bool = False
        self.halted: bool = False

    @property
    def write_fraction(self) -> float:
        return self.writes_used / self.write_budget

    @property
    def read_fraction(self) -> float:
        return self.reads_used / self.read_budget

    def consume_write(self) -> str:
        """Record one write tool call; return budget status message."""
        self.writes_used += 1
        return self._evaluate(self.write_budget, self.writes_used)

    def consume_read(self) -> str:
        """Record one read tool call; return budget status message."""
        self.reads_used += 1
        return self._evaluate(self.read_budget, self.reads_used)

    def _evaluate(self, budget: int, used: int) -> str:
        fraction = used / budget
        if fraction >= self.HARD_HALT_FRACTION:
            self.halted = True
            return self.HALT_MSG
        if fraction >= self.SOFT_NUDGE_FRACTION:
            self.soft_nudged = True
            return self.SOFT_NUDGE_MSG
        return "OK"


# --- 1. write_budget = max(35, line_count // 2) -------------------------------


def test_write_budget_floors_at_35():
    """Small line counts are clamped to the 35 floor."""
    assert DynamicBudget(line_count=0).write_budget == 35
    assert DynamicBudget(line_count=10).write_budget == 35
    assert DynamicBudget(line_count=50).write_budget == 35
    assert DynamicBudget(line_count=68).write_budget == 35  # 68 // 2 = 34


def test_write_budget_boundary_at_70():
    """70 // 2 = 35 -> max(35, 35) = 35 (floor, equal)."""
    assert DynamicBudget(line_count=70).write_budget == 35


def test_write_budget_scales_past_boundary():
    """Once line_count // 2 exceeds 35, the formula dominates."""
    assert DynamicBudget(line_count=80).write_budget == 40
    assert DynamicBudget(line_count=100).write_budget == 50
    assert DynamicBudget(line_count=1000).write_budget == 500


def test_write_budget_integer_division_truncates():
    """Odd line counts truncate via // as expected."""
    assert DynamicBudget(line_count=81).write_budget == 40  # 81 // 2 = 40
    assert DynamicBudget(line_count=83).write_budget == 41  # 83 // 2 = 41
    assert DynamicBudget(line_count=71).write_budget == 35  # 71 // 2 = 35


# --- 2. read_budget = 2 * write_budget ----------------------------------------


def test_read_budget_is_double_write_budget():
    """read_budget == 2 * write_budget across a wide range of line counts."""
    for lc in [0, 1, 35, 70, 71, 80, 81, 100, 500, 1000, 99999]:
        db = DynamicBudget(line_count=lc)
        assert db.read_budget == 2 * db.write_budget


def test_read_budget_floors_at_70():
    """When write_budget floors at 35, read_budget floors at 70."""
    assert DynamicBudget(line_count=0).read_budget == 70
    assert DynamicBudget(line_count=10).read_budget == 70


def test_reads_and_writes_are_independently_tracked():
    """Consuming writes does not increment reads_used and vice-versa."""
    db = DynamicBudget(line_count=80)  # write_budget=40, read_budget=80
    assert db.writes_used == 0
    assert db.reads_used == 0
    db.consume_write()
    assert db.writes_used == 1
    assert db.reads_used == 0
    db.consume_read()
    assert db.writes_used == 1
    assert db.reads_used == 1


# --- 3. Soft nudge fires at 80 % threshold ------------------------------------


def test_no_nudge_below_80_percent():
    """Below 80 % the status is 'OK' and soft_nudged stays False."""
    db = DynamicBudget(line_count=80)  # write_budget = 40, 80 % = 32
    for _ in range(31):                 # 31 / 40 = 77.5 %
        assert db.consume_write() == "OK"
    assert db.soft_nudged is False


def test_nudge_fires_at_exactly_80_percent():
    """At exactly 80 % (32/40) the soft nudge fires."""
    db = DynamicBudget(line_count=80)  # write_budget = 40, 80 % = 32
    for _ in range(31):
        db.consume_write()              # 31 / 40 = 77.5 %
    result = db.consume_write()         # 32 / 40 = 80 %
    assert result == DynamicBudget.SOFT_NUDGE_MSG
    assert db.soft_nudged is True


def test_nudge_fires_at_80_percent_of_read_budget():
    """Soft nudge fires at 80 % of read_budget too."""
    db = DynamicBudget(line_count=80)  # read_budget = 80, 80 % = 64
    for _ in range(63):
        assert db.consume_read() == "OK"
    assert db.soft_nudged is False
    result = db.consume_read()          # 64 / 80 = 80 %
    assert result == DynamicBudget.SOFT_NUDGE_MSG
    assert db.soft_nudged is True


def test_nudge_persists_between_80_and_100_percent():
    """Between 80 % and 100 % the nudge message repeats; no halt yet."""
    db = DynamicBudget(line_count=80)  # write_budget = 40
    for _ in range(31):
        db.consume_write()              # below 80 %
    assert db.consume_write() == DynamicBudget.SOFT_NUDGE_MSG  # 80 %
    # 82.5 % -- still nudging
    assert db.consume_write() == DynamicBudget.SOFT_NUDGE_MSG
    assert db.halted is False


# --- 4. Circuit breaker hard-halts at 100 % ----------------------------------


def test_hard_halt_at_exactly_100_percent():
    """At 100 % (40/40) the circuit breaker fires HALT_MSG."""
    db = DynamicBudget(line_count=80)  # write_budget = 40, 100 % = 40
    for _ in range(39):                 # up to 97.5 %
        db.consume_write()
    assert db.halted is False
    result = db.consume_write()         # 40 / 40 = 100 %
    assert result == DynamicBudget.HALT_MSG
    assert db.halted is True


def test_hard_halt_at_100_percent_of_read_budget():
    """Circuit breaker fires when read_budget is exhausted."""
    db = DynamicBudget(line_count=80)  # read_budget = 80, 100 % = 80
    for _ in range(79):
        assert db.consume_read() != DynamicBudget.HALT_MSG
    assert db.halted is False
    result = db.consume_read()          # 80 / 80 = 100 %
    assert result == DynamicBudget.HALT_MSG
    assert db.halted is True


def test_soft_nudge_does_not_suppress_hard_halt():
    """The nudge at 80 % never suppresses the halt at 100 %."""
    db = DynamicBudget(line_count=80)  # write_budget = 40
    results = [db.consume_write() for _ in range(40)]
    # 32nd call (index 31) = 80 % -> soft nudge
    assert results[31] == DynamicBudget.SOFT_NUDGE_MSG
    # 40th call (index 39) = 100 % -> hard halt
    assert results[39] == DynamicBudget.HALT_MSG
    assert db.halted is True


def test_below_100_percent_does_not_halt():
    """97.5 % usage does NOT trip the circuit breaker."""
    db = DynamicBudget(line_count=80)  # write_budget = 40
    for _ in range(39):                 # 97.5 %
        db.consume_write()
    assert db.halted is False
    assert db.write_fraction == 0.975
