"""Tool confinement for the Orchestrator State Machine (build.md §4, §5c).

Every worker capability is a subprocess wrapper around an existing
`factory/tools/*.py` CLI. Agents NEVER touch the filesystem directly — they
receive only the allow-listed, ACL-wrapped tools the orchestrator hands them.
"""
import contextvars
from pydantic_ai import RunContext

_current_role: contextvars.ContextVar[str | None] = contextvars.ContextVar('orchestrator_current_role', default=None)
_current_agent: contextvars.ContextVar[str | None] = contextvars.ContextVar('orchestrator_current_agent', default=None)

def set_current_role(role: str | None) -> None:
    """Set the active role for the current execution context (used by `remember`)."""
    _current_role.set(role)

def get_current_role() -> str | None:
    """Return the active role, or None if unset."""
    return _current_role.get()

def set_current_agent(agent_id: str | None) -> None:
    """Set the active agent id (coderN) for per-agent memory isolation (ticket a101k)."""
    _current_agent.set(agent_id)

def get_current_agent() -> str | None:
    """Return the active agent id, or None if unset."""
    return _current_agent.get()

def remember(note: str) -> str:
    """Persist a note to THIS agent's OWN history so it survives across turns.

    Because each agent is stateless across turns, call this to record anything
    you need to execute correctly on your next turn (open questions, collisions,
    decisions). The note is appended to your own `<role>.jsonl` (or, for an
    isolated coder agent, `coder/<agent_id>.jsonl`) + `.md` and re-injected as
    context on your next turn. It is separate from `bd` and writes ONLY to your
    own folder — it never leaks to other roles or sibling coders (ticket a101k).

    Args:
        note: The text you want to remember for your next turn.
    """
    role = get_current_role()
    if not role:
        return 'remember: NO active role context — note was NOT persisted. (This tool only works while a role is bound; contact the harness.)'
    try:
        from factory.infra import artefacts
        artefacts.remember_note(role, note, agent_id=get_current_agent())
        return f"remember: note recorded to role '{role}' history (persists across turns)."
    except Exception as exc:
        return f"remember: FAILED to persist note for role '{role}': {exc!r}"

def keep_memory(note: str) -> str:
    """Compacted-memory externalization sink for the cross-turn compaction gate.

    Named alias of `remember`: uses the SAME persistence path (the current_role /
    current_agent contextvars -> `artefacts.remember_note`) so a role only ever
    writes its OWN history. For an isolated coder agent the note lands in its own
    `coder/<agent_id>.jsonl` (keep_memory stays PRIVATE to coderN, ticket a101k).
    The compaction agent has this as its ONLY tool and calls it exactly once with
    the essentials it needs to continue. Do NOT invent a separate persistence path.
    """
    return remember(note)

def record_plan(ctx: RunContext, approach: str) -> str:
    """MUST be called BEFORE applying any edit. State your edit strategy.

    Forces the coder to commit to a concrete approach (which files, what
    change, in what order) before it touches the repo. Without this gate a weak
    model silently research-loops on read-only calls and emits zero writes. The
    plan is echoed to run.log for forensics; the tool itself performs no I/O.
    """
    plan = (approach or '').strip()
    print(f'[CODER PLAN] {plan}', flush=True)
    if not plan:
        return 'No plan provided. Call record_plan again with a concrete edit strategy BEFORE any write/edit tool.'
    return 'Plan acknowledged. You are cleared to investigate further and then apply your edits.'
