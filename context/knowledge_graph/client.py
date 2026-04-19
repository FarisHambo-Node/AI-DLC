"""
Neo4j client wrapper. Exposes a narrow query API (not raw Cypher to callers).

Nodes:   Service, File, Function, Class, Ticket, PR, Deploy, Incident,
         Person, Team, ComplianceRule
Edges:   calls, imports, owns, resolves, introduced_bug, covered_by,
         deployed_to, fixed_by, blocked_by, depends_on
"""

# TODO: class KnowledgeGraphClient
#   - callers_of(symbol) -> list[Node]
#   - callees_of(symbol) -> list[Node]
#   - incidents_in_last(service, days) -> list[Incident]
#   - related_tickets(area, days) -> list[Ticket]
#   - changes_since_deploy(deploy_ref) -> list[File]
