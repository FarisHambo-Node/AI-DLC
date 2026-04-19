"""
Vector store (pgvector). Used for:
  - code-snippet similarity ("how have we done X before?")
  - incident similarity ("have we seen this error pattern before?")
  - doc chunk retrieval for large non-structured pages
"""

# TODO: class VectorStore
#   - search(query_embedding, top_k, filters) -> list[Chunk]
#   - upsert(chunks: list[Chunk])
