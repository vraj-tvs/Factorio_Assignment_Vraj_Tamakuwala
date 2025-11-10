#!/usr/bin/env python3
import json
import sys
from collections import defaultdict, deque


class MaxFlowSolver:
    """Max-flow solver with support for lower bounds and node capacities."""
    
    def __init__(self):
        self.graph = defaultdict(lambda: defaultdict(float))
        self.original_capacity = {}
        self.nodes = set()
    
    def add_edge(self, u, v, capacity):
        """Add directed edge with capacity."""
        self.graph[u][v] += capacity
        self.original_capacity[(u, v)] = self.graph[u][v]
        self.nodes.add(u)
        self.nodes.add(v)
        if v not in self.graph:
            self.graph[v] = defaultdict(float)
        if u not in self.graph:
            self.graph[u] = defaultdict(float)
    
    def bfs(self, source, sink, parent):
        """BFS to find augmenting path, returns True if path exists."""
        visited = {source}
        queue = deque([source])
        
        while queue:
            # Sort for determinism
            u = queue.popleft()
            
            # Sort neighbors for determinism
            neighbors = sorted(self.graph[u].keys())
            for v in neighbors:
                if v not in visited and self.graph[u][v] > 1e-9:
                    visited.add(v)
                    parent[v] = u
                    if v == sink:
                        return True
                    queue.append(v)
        
        return False
    
    def edmonds_karp(self, source, sink):
        """Edmonds-Karp algorithm for max flow."""
        parent = {}
        max_flow = 0
        
        while self.bfs(source, sink, parent):
            # Find minimum capacity along the path
            path_flow = float('inf')
            s = sink
            while s != source:
                path_flow = min(path_flow, self.graph[parent[s]][s])
                s = parent[s]
            
            # Update residual capacities
            v = sink
            while v != source:
                u = parent[v]
                self.graph[u][v] -= path_flow
                self.graph[v][u] += path_flow
                v = parent[v]
            
            max_flow += path_flow
            parent = {}
        
        return max_flow
    
    def get_reachable_from_source(self, source):
        """Get all nodes reachable from source in residual graph."""
        visited = {source}
        queue = deque([source])
        
        while queue:
            u = queue.popleft()
            for v in sorted(self.graph[u].keys()):
                if v not in visited and self.graph[u][v] > 1e-9:
                    visited.add(v)
                    queue.append(v)
        
        return sorted(visited)


def solve_belts(data):
    """Solve the belts flow problem with lower bounds and node caps."""
    
    edges = data["edges"]
    node_caps = data.get("node_caps", {})
    sources = data["sources"]
    sink = data["sink"]
    
    # Step 1: Node splitting for capacity constraints
    # We'll track which nodes need splitting
    split_nodes = {}
    all_nodes = set([sink])
    
    for edge in edges:
        all_nodes.add(edge["from"])
        all_nodes.add(edge["to"])
    
    for source_info in sources:
        all_nodes.add(source_info["node"])
    
    # Identify nodes that need splitting (have caps, not source/sink)
    source_nodes = {s["node"] for s in sources}
    for node in all_nodes:
        if node in node_caps and node != sink and node not in source_nodes:
            split_nodes[node] = f"{node}_out"
    
    # Step 2: Handle lower bounds via circulation problem
    # Transform edges: reduce capacity by lo, track imbalances
    transformed_edges = []
    imbalance = defaultdict(float)
    edge_mapping = {}  # Map (u_actual, v_actual) -> original edge info
    
    for edge in edges:
        u, v = edge["from"], edge["to"]
        lo = edge.get("lo", 0)
        hi = edge["hi"]
        
        # Apply node splitting if needed
        if u in split_nodes:
            u_actual = split_nodes[u]
        else:
            u_actual = u
        
        if v in split_nodes:
            v_actual = f"{v}_in"
        else:
            v_actual = v
        
        # Transform for lower bounds
        transformed_edges.append({
            "from": u_actual,
            "to": v_actual,
            "capacity": hi - lo,
            "original_lo": lo
        })
        
        # Store mapping for flow reconstruction
        edge_mapping[(u_actual, v_actual)] = {
            "original_from": u,
            "original_to": v,
            "lo": lo,
            "hi": hi,
            "transformed_capacity": hi - lo
        }
        
        # Track imbalances due to lower bounds
        imbalance[v_actual] += lo  # v needs lo more (demand)
        imbalance[u_actual] -= lo  # u must supply lo more
    
    # Add edges for split nodes
    split_edges = []
    for node, out_node in split_nodes.items():
        in_node = f"{node}_in"
        cap = node_caps[node]
        split_edges.append({
            "from": in_node,
            "to": out_node,
            "capacity": cap,
            "original_lo": 0
        })
    
    # Step 3: Check lower bound feasibility using dummy edges
    # Add dummy edges to balance imbalances and check if a circulation exists
    # Note: We exclude source nodes and sink from this check, as their imbalances
    # are handled by the actual flow from sources to sink
    
    source_nodes = {s["node"] for s in sources}
    total_dummy_demand = 0
    
    # Filter out imbalances for source nodes and sink
    internal_imbalance = {
        node: imb for node, imb in imbalance.items()
        if node not in source_nodes and node != sink
    }
    
    # Only do feasibility check if there are actual internal imbalances
    if any(abs(imb) > 1e-9 for imb in internal_imbalance.values()):
        dummy_source = "__dummy_source__"
        dummy_sink = "__dummy_sink__"
        
        # Create solver for feasibility check
        solver_feasibility = MaxFlowSolver()
        
        # Add all transformed edges
        for edge in transformed_edges + split_edges:
            solver_feasibility.add_edge(edge["from"], edge["to"], edge["capacity"])
        
        # Add dummy edges to balance internal imbalances only
        for node in sorted(internal_imbalance.keys()):
            imb = internal_imbalance[node]
            if imb > 1e-9:  # Positive imbalance (demand) - node needs flow
                # Add edge FROM dummy_source TO node with capacity = imbalance
                solver_feasibility.add_edge(dummy_source, node, imb)
                total_dummy_demand += imb
            elif imb < -1e-9:  # Negative imbalance (supply) - node has excess flow
                # Add edge FROM node TO dummy_sink with capacity = abs(imbalance)
                solver_feasibility.add_edge(node, dummy_sink, -imb)
        
        # Run max flow from dummy_source to dummy_sink
        max_flow_circulation = solver_feasibility.edmonds_karp(dummy_source, dummy_sink)
        
        # Check if all dummy edges are saturated (lower bounds feasible)
        if abs(max_flow_circulation - total_dummy_demand) > 1e-6:
            # Lower bounds not feasible - some dummy edges couldn't be saturated
            reachable = solver_feasibility.get_reachable_from_source(dummy_source)
            return {
                "status": "infeasible",
                "cut_reachable": [n for n in reachable if n not in [dummy_source, dummy_sink]],
                "deficit": {
                    "demand_balance": round(total_dummy_demand - max_flow_circulation, 2),
                    "tight_nodes": [],
                    "tight_edges": []
                }
            }
    
    # Step 4: Run actual flow from virtual_source to sink
    # Create solver for the main flow problem
    solver2 = MaxFlowSolver()
    
    # Add all transformed edges
    for edge in transformed_edges + split_edges:
        solver2.add_edge(edge["from"], edge["to"], edge["capacity"])
    
    # Calculate total supply, accounting for lower bounds on source edges
    # For each source, reduce its available supply by the sum of lower bounds on its outgoing edges
    adjusted_supply = {}
    for source_info in sources:
        source_node = source_info["node"]
        supply = source_info["supply"]
        
        # Find lower bounds on outgoing edges from this source
        total_lo_from_source = sum(
            edge["lo"] for edge in edges if edge["from"] == source_node
        )
        
        # Adjusted supply = original supply - lower bounds (which are "pre-sent")
        adjusted_supply[source_node] = supply - total_lo_from_source
    
    # Total supply for comparison (original, not adjusted)
    total_supply = sum(s["supply"] for s in sources)
    # Total adjusted supply (what we actually route through the transformed network)
    total_adjusted_supply = sum(adjusted_supply.values())
    
    # Create virtual source and connect to actual sources with adjusted supply
    virtual_source = "__virtual_source__"
    for source_info in sources:
        source_node = source_info["node"]
        solver2.add_edge(virtual_source, source_node, adjusted_supply[source_node])
    
    # Run max flow
    max_flow = solver2.edmonds_karp(virtual_source, sink)
    
    # Check if we can satisfy the demand (compare with adjusted supply)
    if abs(max_flow - total_adjusted_supply) > 1e-6:
        # Infeasible
        reachable = solver2.get_reachable_from_source(virtual_source)
        
        # Find tight edges and nodes
        tight_edges = []
        tight_nodes = []
        
        for node in reachable:
            if node in node_caps:
                # Check if node cap is tight
                in_node = f"{node}_in"
                out_node = split_nodes.get(node, node)
                if in_node in solver2.graph and out_node in solver2.graph[in_node]:
                    if solver2.graph[in_node][out_node] < 1e-9:
                        tight_nodes.append(node)
        
        # Find edges crossing the cut
        for u in reachable:
            if u == virtual_source:
                continue
            for v in solver2.nodes:
                if v not in reachable and (u, v) in solver2.original_capacity:
                    if solver2.graph[u][v] < 1e-9:
                        # Find original edge
                        for edge in edges:
                            u_orig = edge["from"]
                            v_orig = edge["to"]
                            if (u == u_orig or u == split_nodes.get(u_orig)) and \
                               (v == v_orig or v == f"{v_orig}_in"):
                                tight_edges.append({
                                    "from": edge["from"],
                                    "to": edge["to"],
                                    "flow_needed": round(solver2.original_capacity[(u, v)], 2)
                                })
        
        return {
            "status": "infeasible",
            "cut_reachable": [n for n in reachable if n != virtual_source],
            "deficit": {
                "demand_balance": round(total_adjusted_supply - max_flow, 2),
                "tight_nodes": tight_nodes[:2] if tight_nodes else [],
                "tight_edges": tight_edges[:2] if tight_edges else []
            }
        }
    
    # Step 7: Reconstruct original flows
    flows = []
    
    for (u_actual, v_actual), edge_info in edge_mapping.items():
        # Get original edge information
        u_orig = edge_info["original_from"]
        v_orig = edge_info["original_to"]
        lo = edge_info["lo"]
        transformed_cap = edge_info["transformed_capacity"]
        
        # Get current residual capacity from the solved graph
        residual = solver2.graph[u_actual].get(v_actual, 0)
        
        # Flow sent = original transformed capacity - residual capacity
        flow_sent = transformed_cap - residual
        
        # Add back lower bound to get actual flow
        actual_flow = flow_sent + lo
        
        if actual_flow > 1e-9:
            flows.append({
                "from": u_orig,
                "to": v_orig,
                "flow": round(actual_flow, 2)
            })
    
    # Sort flows for determinism
    flows.sort(key=lambda x: (x["from"], x["to"]))
    
    # Calculate actual flow reaching the sink (sum of flows into sink)
    actual_flow_to_sink = sum(
        flow["flow"] for flow in flows if flow["to"] == sink
    )
    
    return {
        "status": "ok",
        "max_flow_per_min": round(actual_flow_to_sink, 2),
        "flows": flows
    }


def main():
    # Read JSON from stdin
    data = json.load(sys.stdin)
    
    # Solve
    result = solve_belts(data)
    
    # Write JSON to stdout
    json.dump(result, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main()

