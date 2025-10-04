#!/usr/bin/env python3
"""
FalkorDB Graph Data Inspector

Connects to FalkorDB and queries the graph to see what entities exist.
Useful for debugging why the AI agent isn't finding data.
"""

import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from falkordb import FalkorDB
from config import settings


def connect_to_falkordb():
    """Connect to FalkorDB using application settings"""
    print(f"🔌 Connecting to FalkorDB...")
    print(f"   Host: {settings.falkordb_host}")
    print(f"   Port: {settings.falkordb_port}")
    print(f"   Database: {settings.falkordb_database}")

    db = FalkorDB(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        username=settings.falkordb_username,
        password=settings.falkordb_password,
    )

    graph = db.select_graph(settings.falkordb_database)
    print("✅ Connected to FalkorDB\n")
    return graph


def run_query(graph, query, description):
    """Run a Cypher query and return results"""
    print(f"📊 {description}")
    print(f"   Query: {query}")
    try:
        result = graph.query(query)
        return result
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        return None


def main():
    print("=" * 80)
    print("FalkorDB Graph Data Inspector")
    print("=" * 80)
    print()

    graph = connect_to_falkordb()

    # Query 1: Count all nodes
    print("-" * 80)
    result = run_query(
        graph,
        "MATCH (n) RETURN count(n) as total_nodes",
        "Total Nodes in Graph"
    )
    if result:
        for record in result.result_set:
            print(f"   ✅ Total nodes: {record[0]}\n")

    # Query 2: Count nodes by label
    print("-" * 80)
    result = run_query(
        graph,
        "MATCH (n) RETURN labels(n)[0] as label, count(n) as count ORDER BY count DESC",
        "Node Count by Label"
    )
    if result:
        print(f"   {'Label':<20} {'Count':>10}")
        print(f"   {'-'*20} {'-'*10}")
        for record in result.result_set:
            label = record[0] if record[0] else "(no label)"
            count = record[1]
            print(f"   {label:<20} {count:>10}")
        print()

    # Query 3: Count all relationships
    print("-" * 80)
    result = run_query(
        graph,
        "MATCH ()-[r]->() RETURN count(r) as total_relationships",
        "Total Relationships in Graph"
    )
    if result:
        for record in result.result_set:
            print(f"   ✅ Total relationships: {record[0]}\n")

    # Query 4: Count relationships by type
    print("-" * 80)
    result = run_query(
        graph,
        "MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as count ORDER BY count DESC LIMIT 10",
        "Top 10 Relationship Types"
    )
    if result:
        print(f"   {'Relationship Type':<30} {'Count':>10}")
        print(f"   {'-'*30} {'-'*10}")
        for record in result.result_set:
            rel_type = record[0]
            count = record[1]
            print(f"   {rel_type:<30} {count:>10}")
        print()

    # Query 5: Sample of Entity nodes with properties
    print("-" * 80)
    result = run_query(
        graph,
        """MATCH (n:Entity)
           RETURN n.name as name,
                  n.created_at as created_at,
                  n.group_id as group_id
           ORDER BY n.created_at DESC
           LIMIT 10""",
        "Most Recent 10 Entities"
    )
    if result:
        print(f"   {'Entity Name':<40} {'Created At':<25} {'Group ID':<20}")
        print(f"   {'-'*40} {'-'*25} {'-'*20}")
        for record in result.result_set:
            name = str(record[0])[:40] if record[0] else "(no name)"
            created_at = str(record[1])[:25] if record[1] else "(no timestamp)"
            group_id = str(record[2])[:20] if record[2] else "(no group)"
            print(f"   {name:<40} {created_at:<25} {group_id:<20}")
        print()

    # Query 6: Check for email-related entities
    print("-" * 80)
    result = run_query(
        graph,
        """MATCH (n:Entity)
           WHERE n.name CONTAINS 'email' OR
                 n.name CONTAINS 'gmail' OR
                 n.name CONTAINS 'message' OR
                 n.name CONTAINS '@'
           RETURN n.name as name, n.group_id as group_id
           LIMIT 20""",
        "Email-Related Entities (contains: email, gmail, message, @)"
    )
    if result:
        count = len(result.result_set)
        print(f"   Found {count} email-related entities:")
        for record in result.result_set:
            name = record[0]
            group_id = record[1] if record[1] else "(no group)"
            print(f"   - {name} [Group: {group_id}]")
        print()

    # Query 7: List all unique group_ids
    print("-" * 80)
    result = run_query(
        graph,
        """MATCH (n:Entity)
           WHERE n.group_id IS NOT NULL
           RETURN DISTINCT n.group_id as group_id
           ORDER BY group_id""",
        "All Unique Group IDs"
    )
    if result:
        group_ids = [record[0] for record in result.result_set]
        print(f"   Found {len(group_ids)} unique group IDs:")
        for gid in group_ids:
            print(f"   - {gid}")
        print()

    # Query 8: Entity count by group_id with timestamps
    print("-" * 80)
    result = run_query(
        graph,
        """MATCH (n:Entity)
           RETURN n.group_id as group_id,
                  count(n) as entity_count,
                  max(n.created_at) as most_recent
           ORDER BY most_recent DESC""",
        "Entity Count by Group ID (Most Recent First)"
    )
    if result:
        print(f"   {'Group ID':<35} {'Entities':>10} {'Most Recent':<25}")
        print(f"   {'-'*35} {'-'*10} {'-'*25}")
        for record in result.result_set:
            group_id = record[0] if record[0] else "(no group)"
            count = record[1]
            most_recent = str(record[2])[:25] if record[2] else "(no timestamp)"
            print(f"   {str(group_id):<35} {count:>10} {most_recent:<25}")
        print()

    # Query 9: Sample Episodic nodes (FIXED: was Episode)
    print("-" * 80)
    result = run_query(
        graph,
        """MATCH (e:Episodic)
           RETURN e.name as name,
                  e.content as content,
                  e.created_at as created_at,
                  e.group_id as group_id
           ORDER BY e.created_at DESC
           LIMIT 5""",
        "Most Recent 5 Episodic Nodes"
    )
    if result:
        print(f"   Found {len(result.result_set)} episodes:")
        for i, record in enumerate(result.result_set, 1):
            name = record[0]
            content = str(record[1])[:100] if record[1] else "(no content)"
            created_at = record[2]
            group_id = record[3] if record[3] else "(no group)"
            print(f"\n   Episode {i}:")
            print(f"   - Name: {name}")
            print(f"   - Content: {content}...")
            print(f"   - Created: {created_at}")
            print(f"   - Group: {group_id}")
        print()

    print("=" * 80)
    print("Inspection Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
