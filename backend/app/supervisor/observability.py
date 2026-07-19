"""
Execution-ID logging correlation - M7.3. The DEBUGGING half of execution
identity, deliberately separate from the PERSISTED half
(SupervisionState.execution_id, base.py). Replay/audit needs durable
structured state (SupervisionState.history already is that); correlating
a specific provider call in production logs back to the plan run that
caused it is a different job, served here via a contextvars-based
correlation id plus a logging.Filter - the same idiom typically used for
request IDs in web services.

Deliberately NOT implemented by threading an `execution_id` field through
GatewayRequest/AgentInput/every other core dataclass in the stack - that
would touch and widen every already-approved M7.2 type for a concern
those types don't otherwise need to know about (does ProviderClient
really need to understand "a Supervisor execution" as a concept? no).
Instead: SupervisorRuntime sets a contextvar for the duration of one
agent invocation (see runtime.py's own _invoke_one()); a process-wide
logging.Filter reads it and stamps EVERY log record - including every
pre-existing logger.warning()/info() call in app.ai_gateway.client and
elsewhere - with zero changes to any of those call sites. Outside a
Supervisor-driven call (e.g. direct AgentRuntime.run() usage, or M7.2's
own test suite), the contextvar is unset and the stamped field is simply
None - unchanged, invisible behavior for every non-Supervisor caller.

Wiring the filter onto the root/app logger is a one-line addition at
whatever process entrypoint configures logging (see
install_execution_id_log_filter() below) - not wired automatically by
importing this module, so importing app.supervisor never has a
side-effect on global logging configuration.
"""
import logging
from contextvars import ContextVar

_current_execution_id: ContextVar[str | None] = ContextVar("supervisor_execution_id", default=None)


def current_execution_id() -> str | None:
    return _current_execution_id.get()


class ExecutionIdContext:
    """Context manager - sets the current execution id for the duration
    of the `with` block, restoring whatever was set before on exit (so
    nested/sequential Supervisor executions in the same process, e.g. a
    test suite running many plans back to back, never leak one
    execution's id into another's log lines)."""

    def __init__(self, execution_id: str | None):
        self._execution_id = execution_id
        self._token = None

    def __enter__(self) -> "ExecutionIdContext":
        self._token = _current_execution_id.set(self._execution_id)
        return self

    def __exit__(self, *exc_info) -> None:
        _current_execution_id.reset(self._token)


class ExecutionIdLogFilter(logging.Filter):
    """Stamps `record.execution_id` on every log record that passes
    through it, read from the contextvar above. Install once, on the
    root logger or any handler, at process startup - see module
    docstring. A record's `execution_id` is None whenever no
    Supervisor-driven call is currently in progress on this thread."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.execution_id = current_execution_id()
        return True


def install_execution_id_log_filter(logger: logging.Logger | None = None) -> None:
    """Idempotent - safe to call more than once; will not attach a
    second identical filter to the same handler. `logger` defaults to
    the root logger, which is what app.main's own logging.basicConfig()
    configures.

    Deliberately attached to the logger's HANDLER(S), not to the Logger
    object itself: a Filter attached directly to a Logger only runs for
    records logged THROUGH that exact logger, not for records from other
    loggers that merely propagate up to it (e.g.
    app.ai_gateway.client's own `logging.getLogger(__name__)`) - only a
    Filter on the HANDLER that ultimately emits the record runs for
    every record that reaches it, regardless of which logger originated
    it. Since logging.basicConfig() installs exactly one handler on the
    root logger and everything propagates there by default, attaching to
    the root logger's handlers is what actually makes this "every
    layer's existing logging picks it up automatically," as intended."""
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if not any(isinstance(existing, ExecutionIdLogFilter) for existing in handler.filters):
            handler.addFilter(ExecutionIdLogFilter())
