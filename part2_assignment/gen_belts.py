#!/usr/bin/env python3
"""
Belts input generator - creates various test cases for flow network optimization.

Usage:
    python gen_belts.py simple
    python gen_belts.py parallel
    python gen_belts.py bottleneck
    python gen_belts.py lower-bounds
    python gen_belts.py grid
    python gen_belts.py large
"""

import json
import sys
import random


def generate_simple():
    """Generate a simple single-path flow."""
    return {
        "edges": [
            {"from": "source", "to": "sink", "lo": 0, "hi": 1000}
        ],
        "sources": [
            {"node": "source", "supply": 500}
        ],
        "sink": "sink"
    }


def generate_parallel():
    """Generate parallel paths from sources to sink."""
    return {
        "edges": [
            {"from": "s1", "to": "a", "lo": 0, "hi": 1000},
            {"from": "s2", "to": "a", "lo": 0, "hi": 800},
            {"from": "a", "to": "b", "lo": 0, "hi": 900},
            {"from": "a", "to": "c", "lo": 0, "hi": 600},
            {"from": "b", "to": "sink", "lo": 0, "hi": 1000},
            {"from": "c", "to": "sink", "lo": 0, "hi": 1000}
        ],
        "sources": [
            {"node": "s1", "supply": 900},
            {"node": "s2", "supply": 600}
        ],
        "sink": "sink"
    }


def generate_bottleneck():
    """Generate a network with a bottleneck edge."""
    return {
        "edges": [
            {"from": "s1", "to": "a", "lo": 0, "hi": 1000},
            {"from": "s2", "to": "a", "lo": 0, "hi": 1000},
            {"from": "a", "to": "bottleneck", "lo": 0, "hi": 500},  # Bottleneck
            {"from": "bottleneck", "to": "b", "lo": 0, "hi": 1000},
            {"from": "b", "to": "sink", "lo": 0, "hi": 1000}
        ],
        "sources": [
            {"node": "s1", "supply": 600},
            {"node": "s2", "supply": 400}
        ],
        "sink": "sink"
    }


def generate_lower_bounds():
    """Generate a network with lower bound constraints."""
    return {
        "edges": [
            {"from": "s1", "to": "a", "lo": 100, "hi": 500},  # Must use at least 100
            {"from": "s2", "to": "b", "lo": 50, "hi": 400},
            {"from": "a", "to": "c", "lo": 0, "hi": 600},
            {"from": "b", "to": "c", "lo": 0, "hi": 600},
            {"from": "c", "to": "sink", "lo": 150, "hi": 1000}  # Must deliver at least 150
        ],
        "sources": [
            {"node": "s1", "supply": 500},
            {"node": "s2", "supply": 400}
        ],
        "sink": "sink"
    }


def generate_node_caps():
    """Generate a network with node capacity constraints."""
    return {
        "edges": [
            {"from": "s1", "to": "hub", "lo": 0, "hi": 1000},
            {"from": "s2", "to": "hub", "lo": 0, "hi": 1000},
            {"from": "hub", "to": "d1", "lo": 0, "hi": 1000},
            {"from": "hub", "to": "d2", "lo": 0, "hi": 1000},
            {"from": "d1", "to": "sink", "lo": 0, "hi": 1000},
            {"from": "d2", "to": "sink", "lo": 0, "hi": 1000}
        ],
        "node_caps": {
            "hub": 800  # Hub can only handle 800 items/min throughput
        },
        "sources": [
            {"node": "s1", "supply": 600},
            {"node": "s2", "supply": 600}
        ],
        "sink": "sink"
    }


def generate_grid(rows=3, cols=3, capacity=100, supply_per_source=150):
    """Generate a grid network."""
    edges = []
    sources = []
    
    # Create grid nodes
    def node_name(r, c):
        return f"n_{r}_{c}"
    
    # Horizontal edges
    for r in range(rows):
        for c in range(cols - 1):
            edges.append({
                "from": node_name(r, c),
                "to": node_name(r, c + 1),
                "lo": 0,
                "hi": capacity
            })
    
    # Vertical edges
    for r in range(rows - 1):
        for c in range(cols):
            edges.append({
                "from": node_name(r, c),
                "to": node_name(r + 1, c),
                "lo": 0,
                "hi": capacity
            })
    
    # Sources on the left edge
    for r in range(rows):
        sources.append({
            "node": node_name(r, 0),
            "supply": supply_per_source
        })
    
    # Sink at bottom right
    sink = node_name(rows - 1, cols - 1)
    
    return {
        "edges": edges,
        "sources": sources,
        "sink": sink
    }


def generate_large(num_nodes=20, edge_density=0.3, seed=42):
    """Generate a large random network."""
    random.seed(seed)
    
    edges = []
    sources = []
    num_sources = max(2, num_nodes // 10)
    
    # Create nodes (excluding source and sink)
    intermediate_nodes = [f"n{i}" for i in range(num_nodes - num_sources - 1)]
    source_nodes = [f"s{i}" for i in range(num_sources)]
    sink = "sink"
    
    all_nodes = source_nodes + intermediate_nodes
    
    # Add sources
    for src in source_nodes:
        sources.append({
            "node": src,
            "supply": random.randint(100, 500)
        })
    
    # Create edges with controlled density
    # Ensure connectivity by creating a spanning path
    current_nodes = source_nodes[:]
    remaining_nodes = intermediate_nodes + [sink]
    
    while remaining_nodes:
        from_node = random.choice(current_nodes)
        to_node = remaining_nodes.pop(0)
        
        edges.append({
            "from": from_node,
            "to": to_node,
            "lo": 0,
            "hi": random.randint(100, 800)
        })
        
        current_nodes.append(to_node)
    
    # Add additional random edges for density
    num_extra_edges = int(len(all_nodes) * len(all_nodes) * edge_density)
    
    for _ in range(num_extra_edges):
        from_node = random.choice(all_nodes)
        to_candidates = [n for n in all_nodes + [sink] if n != from_node]
        to_node = random.choice(to_candidates)
        
        # Check if edge already exists
        if not any(e["from"] == from_node and e["to"] == to_node for e in edges):
            edges.append({
                "from": from_node,
                "to": to_node,
                "lo": 0,
                "hi": random.randint(100, 800)
            })
    
    return {
        "edges": edges,
        "sources": sources,
        "sink": sink
    }


def generate_infeasible():
    """Generate an infeasible problem due to insufficient capacity."""
    return {
        "edges": [
            {"from": "s1", "to": "bottleneck", "lo": 0, "hi": 1000},
            {"from": "s2", "to": "bottleneck", "lo": 0, "hi": 1000},
            {"from": "bottleneck", "to": "sink", "lo": 0, "hi": 300}  # Too small
        ],
        "sources": [
            {"node": "s1", "supply": 500},
            {"node": "s2", "supply": 500}
        ],
        "sink": "sink"
    }


def generate_balanced():
    """Generate a perfectly balanced network."""
    return {
        "edges": [
            {"from": "s1", "to": "a", "lo": 0, "hi": 250},
            {"from": "s1", "to": "b", "lo": 0, "hi": 250},
            {"from": "s2", "to": "c", "lo": 0, "hi": 250},
            {"from": "s2", "to": "d", "lo": 0, "hi": 250},
            {"from": "a", "to": "sink", "lo": 0, "hi": 250},
            {"from": "b", "to": "sink", "lo": 0, "hi": 250},
            {"from": "c", "to": "sink", "lo": 0, "hi": 250},
            {"from": "d", "to": "sink", "lo": 0, "hi": 250}
        ],
        "sources": [
            {"node": "s1", "supply": 500},
            {"node": "s2", "supply": 500}
        ],
        "sink": "sink"
    }


def main():
    generators = {
        "simple": ("Simple single path", generate_simple),
        "parallel": ("Parallel paths network", generate_parallel),
        "bottleneck": ("Network with bottleneck", generate_bottleneck),
        "lower-bounds": ("Network with lower bound constraints", generate_lower_bounds),
        "node-caps": ("Network with node capacity constraints", generate_node_caps),
        "grid": ("Grid network (3x3)", lambda: generate_grid(3, 3)),
        "large": ("Large random network (20 nodes)", lambda: generate_large(20, 0.3)),
        "infeasible": ("Infeasible problem", generate_infeasible),
        "balanced": ("Perfectly balanced network", generate_balanced),
    }
    
    if len(sys.argv) < 2:
        print("Belts Input Generator")
        print("=" * 60)
        print("\nUsage: python gen_belts.py <type>")
        print("\nAvailable types:")
        for key, (desc, _) in generators.items():
            print(f"  {key:20} - {desc}")
        print("\nExamples:")
        print("  python gen_belts.py simple > input.json")
        print("  python gen_belts.py grid | python belts/main.py")
        sys.exit(1)
    
    gen_type = sys.argv[1].lower()
    
    if gen_type not in generators:
        print(f"Error: Unknown type '{gen_type}'")
        print(f"Available types: {', '.join(generators.keys())}")
        sys.exit(1)
    
    _, generator = generators[gen_type]
    input_data = generator()
    
    print(json.dumps(input_data, indent=2))


if __name__ == "__main__":
    main()

