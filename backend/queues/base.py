"""
Queue base class — thin wrapper around Redis lists / streams.
Holds TaskContract ids; the contracts themselves are persisted separately.
"""

# TODO: class Queue
#   - push(task_contract) / pop() / peek()
#   - status counts, ownership tracking
#   - pub/sub for FE websocket updates
