"""
Base class for all agent containers.

Every agent is essentially: a HarnessRuntime + a restricted tool bundle +
a set of skills it is allowed to invoke.
"""

from schemas import TaskContract

# TODO: implement BaseAgent:
#   - __init__(harness_runtime, allowed_skills, allowed_tools)
#   - execute(task: TaskContract) -> TaskContract  (delegates to harness)
#   - lifecycle hooks: on_start, on_complete, on_error
