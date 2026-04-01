"""
Graph schema definitions.

Defines the Cypher statements to create constraints and indexes for the
code knowledge graph. Run once when the database is first initialised.

Node labels:
  File     — a source file in the project
  Function — a function or method definition
  Class    — a class, struct, enum, or interface
  Module   — a module or namespace

Relationship types:
  CONTAINS   — (File)-[:CONTAINS]->(Function|Class)
  IMPORTS    — (File)-[:IMPORTS]->(File|Module)
  CALLS      — (Function)-[:CALLS]->(Function)
  EXTENDS    — (Class)-[:EXTENDS]->(Class)
  IMPLEMENTS — (Class)-[:IMPLEMENTS]->(Class)
"""

SCHEMA_CYPHER = """
// Constraints (enforce uniqueness)
CREATE CONSTRAINT file_path_unique IF NOT EXISTS
    FOR (f:File) REQUIRE f.path IS UNIQUE;

CREATE CONSTRAINT function_id_unique IF NOT EXISTS
    FOR (fn:Function) REQUIRE fn.id IS UNIQUE;

CREATE CONSTRAINT class_id_unique IF NOT EXISTS
    FOR (c:Class) REQUIRE c.id IS UNIQUE;

// Indexes for fast lookups
CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language);
CREATE INDEX function_name IF NOT EXISTS FOR (fn:Function) ON (fn.name);
CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name);
CREATE INDEX function_complexity IF NOT EXISTS FOR (fn:Function) ON (fn.cyclomatic);
"""

CLEAR_GRAPH_CYPHER = """
MATCH (n) DETACH DELETE n;
"""
