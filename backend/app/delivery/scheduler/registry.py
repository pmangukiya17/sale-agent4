"""
SchedulingPolicy registry - exact mirror of every other provider registry
in this codebase (discovery/providers/registry.py,
outreach/channels/registry.py). Adding a policy is an import + a dict
entry here, never a change to worker.py.
"""
from app.delivery.scheduler.policy import FIFOSchedulingPolicy, SchedulingPolicy

SCHEDULING_POLICY_REGISTRY: dict[str, type[SchedulingPolicy]] = {
    FIFOSchedulingPolicy.key: FIFOSchedulingPolicy,
}


def get_scheduling_policy(policy_key: str) -> SchedulingPolicy:
    policy_cls = SCHEDULING_POLICY_REGISTRY.get(policy_key)
    if policy_cls is None:
        raise KeyError(f"Unknown scheduling policy '{policy_key}'. Registered policies: {list(SCHEDULING_POLICY_REGISTRY)}")
    return policy_cls()
