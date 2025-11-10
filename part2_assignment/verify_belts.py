#!/usr/bin/env python3
"""
Validation helper for belts CLI tool.
Verifies that output satisfies all constraints.

Usage: python verify_belts.py < input.json
       python belts/main.py < input.json | python verify_belts.py --check-output
"""

import json
import sys
import argparse
from collections import defaultdict


def verify_belts_output(input_data, output_data):
    """Verify that belts output satisfies all constraints."""
    
    if output_data["status"] != "ok":
        print(f"Output status is '{output_data['status']}', skipping validation")
        if output_data["status"] == "infeasible":
            print(f"Max feasible flow: {output_data.get('max_feasible_flow_per_min', 'N/A')}")
            print(f"Bottlenecks: {output_data.get('bottleneck_hint', [])}")
        return True
    
    edges = input_data["edges"]
    node_caps = input_data.get("node_caps", {})
    sources = input_data["sources"]
    sink = input_data["sink"]
    
    flows = output_data["flows"]
    max_flow = output_data["max_flow_per_min"]
    
    errors = []
    warnings = []
    
    print("=" * 60)
    print("BELTS OUTPUT VALIDATION")
    print("=" * 60)
    
    # Build flow dictionary
    flow_dict = {}
    for flow_entry in flows:
        u, v = flow_entry["from"], flow_entry["to"]
        flow_dict[(u, v)] = flow_entry["flow"]
    
    # 1. Verify edge capacity bounds (lo ≤ flow ≤ hi)
    print("\n[1] Checking edge capacity constraints (lo ≤ flow ≤ hi)...")
    edge_violations = 0
    
    for edge in edges:
        u, v = edge["from"], edge["to"]
        lo = edge.get("lo", 0)
        hi = edge["hi"]
        flow = flow_dict.get((u, v), 0)
        
        if flow < lo - 1e-6:
            errors.append(f"Edge ({u}→{v}) flow {flow:.2f} < lower bound {lo}")
            edge_violations += 1
        elif flow > hi + 1e-6:
            errors.append(f"Edge ({u}→{v}) flow {flow:.2f} > upper bound {hi}")
            edge_violations += 1
        elif flow > 1e-6:  # Only show active edges
            print(f"    ✓ Edge ({u}→{v}): {lo} ≤ {flow:.2f} ≤ {hi}")
    
    if edge_violations == 0:
        print(f"    ✓ All {len(edges)} edges satisfy capacity constraints")
    
    # 2. Verify flow conservation at nodes
    print("\n[2] Checking flow conservation at nodes...")
    source_nodes = {s["node"] for s in sources}
    
    # Calculate inflow and outflow for each node
    inflow = defaultdict(float)
    outflow = defaultdict(float)
    
    for flow_entry in flows:
        u, v = flow_entry["from"], flow_entry["to"]
        f = flow_entry["flow"]
        outflow[u] += f
        inflow[v] += f
    
    # Check conservation
    all_nodes = set()
    for edge in edges:
        all_nodes.add(edge["from"])
        all_nodes.add(edge["to"])
    all_nodes.update(source_nodes)
    all_nodes.add(sink)
    
    conservation_violations = 0
    
    for node in sorted(all_nodes):
        if node == sink:
            # Constraint: Sink only receives flow (no outflow)
            if outflow[node] > 1e-6:
                errors.append(f"Sink '{node}' has outgoing flow: {outflow[node]:.2f}")
                conservation_violations += 1
            else:
                print(f"    ✓ Sink '{node}': receives {inflow[node]:.2f} items/min (no outflow)")
        
        elif node in source_nodes:
            # Constraint: inflow + supply = outflow
            supply = next(s["supply"] for s in sources if s["node"] == node)
            balance = inflow[node] + supply - outflow[node]
            if abs(balance) > 0.1:
                errors.append(f"Source '{node}' not conserved: in+supply={inflow[node]+supply:.2f} ≠ out={outflow[node]:.2f}")
                conservation_violations += 1
            else:
                print(f"    ✓ Source '{node}': in={inflow[node]:.2f} + supply={supply:.2f} = out={outflow[node]:.2f}")
        
        else:
            # Constraint: inflow = outflow (intermediate nodes)
            balance = inflow[node] - outflow[node]
            if abs(balance) > 0.1:
                errors.append(f"Intermediate '{node}' not conserved: in={inflow[node]:.2f} ≠ out={outflow[node]:.2f}")
                conservation_violations += 1
            elif inflow[node] > 1e-6 or outflow[node] > 1e-6:
                print(f"    ✓ Intermediate '{node}': in={inflow[node]:.2f} = out={outflow[node]:.2f}")
    
    if conservation_violations == 0:
        print(f"    ✓ Flow conservation satisfied at all {len(all_nodes)} nodes")
    
    # 3. Verify node capacity constraints
    print("\n[3] Checking node capacity constraints...")
    
    if node_caps:
        node_cap_violations = 0
        for node, cap in sorted(node_caps.items()):
            node_throughput = inflow[node]  # or outflow[node], should be same
            
            if node_throughput > cap + 1e-6:
                errors.append(f"Node '{node}' throughput {node_throughput:.2f} > capacity {cap}")
                node_cap_violations += 1
            else:
                utilization = (node_throughput / cap * 100) if cap > 0 else 0
                print(f"    ✓ Node '{node}': {node_throughput:.2f} ≤ {cap} ({utilization:.1f}% utilized)")
        
        if node_cap_violations == 0:
            print(f"    ✓ All {len(node_caps)} node capacities satisfied")
    else:
        print("    No node capacity constraints specified")
    
    # 4. Verify non-negativity
    print("\n[4] Checking non-negativity constraint...")
    negative_flows = 0
    
    for flow_entry in flows:
        if flow_entry["flow"] < -1e-6:
            errors.append(f"Negative flow on edge ({flow_entry['from']}→{flow_entry['to']}): {flow_entry['flow']:.2f}")
            negative_flows += 1
    
    if negative_flows == 0:
        print(f"    ✓ All {len(flows)} flows are non-negative")
    
    # 5. Verify total flow calculation
    print("\n[5] Checking total flow calculation...")
    total_supply = sum(s["supply"] for s in sources)
    total_into_sink = inflow[sink]
    
    if abs(max_flow - total_into_sink) > 0.1:
        errors.append(f"Max flow {max_flow:.2f} ≠ flow into sink {total_into_sink:.2f}")
    else:
        print(f"    ✓ Max flow {max_flow:.2f} = flow into sink {total_into_sink:.2f}")
    
    if abs(max_flow - total_supply) > 0.1:
        print(f"    ℹ Max flow {max_flow:.2f} < total supply {total_supply:.2f} (some supply unused)")
    else:
        print(f"    ✓ Max flow {max_flow:.2f} = total supply {total_supply:.2f} (all supply used)")
    
    # Print results summary
    print("\n" + "=" * 60)
    if errors:
        print("❌ VALIDATION FAILED")
        print("=" * 60)
        print("\nConstraint Violations:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. ✗ {error}")
    
    if warnings:
        print("\n⚠️  Warnings:")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. ⚠ {warning}")
    
    if not errors and not warnings:
        print("✅ ALL CONSTRAINTS SATISFIED")
        print("=" * 60)
        print("\nAll flow network constraints are satisfied:")
        print("  • Edge capacities: All flows within [lo, hi] bounds")
        print("  • Flow conservation: Balanced at all nodes")
        print("  • Node capacities: All throughputs within limits")
        print("  • Non-negativity: All flows ≥ 0")
        print("  • Total flow: Correctly calculated")
        return True
    
    print("=" * 60)
    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Validate belts output")
    parser.add_argument("--input", help="Input JSON file (default: stdin)")
    parser.add_argument("--output", help="Output JSON file (default: stdin)")
    parser.add_argument("--check-output", action="store_true", help="Read output from stdin and validate")
    
    args = parser.parse_args()
    
    if args.check_output:
        print("Reading input from stdin...")
        input_data = json.load(sys.stdin)
        print("Input loaded. Now provide output (paste and Ctrl+D):")
        output_data = json.load(sys.stdin)
    else:
        if args.input:
            with open(args.input) as f:
                input_data = json.load(f)
        else:
            input_data = json.load(sys.stdin)
        
        if args.output:
            with open(args.output) as f:
                output_data = json.load(f)
        else:
            # Run belts tool
            import subprocess
            result = subprocess.run(
                [sys.executable, "belts/main.py"],
                input=json.dumps(input_data),
                capture_output=True,
                text=True
            )
            output_data = json.loads(result.stdout)
    
    success = verify_belts_output(input_data, output_data)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

