#!/usr/bin/env python3
import json
import sys
import math
from collections import defaultdict, deque
from pulp import LpProblem, LpMinimize, LpVariable, LpStatus, PULP_CBC_CMD


def solve_factory(data):
    """Solve factory optimization using graph-based backward propagation from target."""
    
    machines = data["machines"]
    recipes = data["recipes"]
    modules = data.get("modules", {})
    limits = data["limits"]
    target = data["target"]
    
    raw_supply = limits["raw_supply_per_min"]
    max_machines = limits["max_machines"]
    target_item = target["item"]
    target_rate = target["rate_per_min"]
    
    # Calculate effective crafts per minute for each recipe
    def get_eff_crafts_per_min(recipe):
        machine_type = recipe["machine"]
        base_speed = machines[machine_type]["crafts_per_min"]
        time_s = recipe["time_s"]
        module = modules.get(machine_type, {})
        speed_mult = 1 + module.get("speed", 0)
        return (base_speed * speed_mult * 60) / time_s
    
    # Get productivity multiplier for each recipe
    def get_prod_mult(recipe):
        machine_type = recipe["machine"]
        module = modules.get(machine_type, {})
        return 1 + module.get("prod", 0)
    
    # Build graph with two types of nodes: items and machines/recipes
    # Edges: output_item -> recipe/machine -> input_item
    
    # Forward edges: item -> list of recipes that consume it
    item_to_recipes = defaultdict(list)  # item -> [recipe_name]
    # Backward edges: item -> list of recipes that produce it
    item_from_recipes = defaultdict(list)  # item -> [recipe_name]
    # Recipe inputs/outputs stored directly in recipes dict
    
    for recipe_name, recipe in recipes.items():
        # Edge: output_item -> recipe
        for out_item in recipe.get("out", {}):
            item_from_recipes[out_item].append(recipe_name)
        # Edge: recipe -> input_item
        for in_item in recipe.get("in", {}):
            item_to_recipes[in_item].append(recipe_name)
    
    # Identify raw materials (not produced by any recipe)
    all_items = set()
    for recipe in recipes.values():
        all_items.update(recipe.get("in", {}).keys())
        all_items.update(recipe.get("out", {}).keys())
        all_items.update(recipe.get("machine")) # add machine to all items
    
    raw_items = {item for item in all_items if item not in item_from_recipes}
    
    # Backward propagation: start from target, calculate required rates
    # We'll try to find integer machine counts
    
    def try_solve_with_target(target_rate_scaled):
        """Try to solve for a given target rate, returning machine counts if feasible."""
        
        # item_demand[item] = total demand rate for that item
        item_demand = defaultdict(float)
        item_demand[target_item] = target_rate_scaled
        
        # recipe_crafts[recipe_name] = crafts per minute for that recipe
        recipe_crafts = defaultdict(float)
        
        # Backward traversal through graph: item -> recipe (machine) -> input_items
        # Start from target item and propagate demand backward through machines
        visited_items = set()
        visited_recipes = set()
        queue = deque([('item', target_item)])
        
        while queue:
            node_type, node_id = queue.popleft()
            
            if node_type == 'item':
                if node_id in visited_items or node_id in raw_items:
                    continue
                visited_items.add(node_id)
                
                # Get demand for this item
                demand = item_demand[node_id]
                if demand <= 1e-9:
                    continue
                
                # Traverse edge: item <- recipe (find recipes that produce this item)
                producing_recipes = item_from_recipes.get(node_id, [])
                if not producing_recipes:
                    continue
                
                # Use first recipe that produces this item
                recipe_name = producing_recipes[0]
                
                # Add recipe node to queue for processing
                queue.append(('recipe', recipe_name))
                
            elif node_type == 'recipe':
                recipe_name = node_id
                if recipe_name in visited_recipes:
                    continue
                visited_recipes.add(recipe_name)
                
                recipe = recipes[recipe_name]
                
                # At machine node: do calculations
                # Find which output item triggered this recipe
                output_item = None
                for out_item in recipe.get("out", {}):
                    if item_demand[out_item] > 1e-9:
                        output_item = out_item
                        break
                
                if not output_item:
                    continue
                
                demand = item_demand[output_item]
                out_qty = recipe["out"][output_item]
                prod_mult = get_prod_mult(recipe)
                effective_output_per_craft = out_qty * prod_mult
                
                # Calculate crafts needed at this machine
                crafts_needed = demand / effective_output_per_craft
                recipe_crafts[recipe_name] += crafts_needed
                
                # Traverse edges: recipe -> input_items (propagate demand)
                for in_item, in_qty in recipe.get("in", {}).items():
                    item_demand[in_item] += crafts_needed * in_qty
                    # Add input item to queue
                    queue.append(('item', in_item))
        
        # Calculate machine counts (keep as decimals)
        machine_counts = defaultdict(float)
        for recipe_name, crafts in recipe_crafts.items():
            recipe = recipes[recipe_name]
            machine_type = recipe["machine"]
            eff_crafts = get_eff_crafts_per_min(recipe)
            machines_needed = crafts / eff_crafts
            machine_counts[machine_type] += machines_needed
        
        # Check constraints
        # 1. Machine limits
        for machine_type, count in machine_counts.items():
            if count > max_machines.get(machine_type, float('inf')):
                return None  # Exceeds machine limit
        
        # 2. Raw material limits
        raw_consumption = {}
        for item in raw_items:
            consumption = item_demand.get(item, 0.0)
            if consumption > 1e-9:
                if consumption > raw_supply.get(item, 0.0) + 1e-9:
                    return None  # Exceeds raw supply
                raw_consumption[item] = consumption
        
        # Calculate effective output rates (crafts * productivity multiplier)
        effective_output = {}
        for recipe_name in recipe_crafts.keys():
            recipe = recipes[recipe_name]
            prod_mult = get_prod_mult(recipe)
            # Multiply crafts by productivity to get actual item output rate
            effective_output[recipe_name] = recipe_crafts[recipe_name] * prod_mult
        
        return {
            "status": "ok",
            "per_recipe_crafts_per_min": dict(effective_output),
            "per_machine_counts": dict(machine_counts),
            "raw_consumption_per_min": raw_consumption
        }
    
    # Try to solve with the target rate
    result = try_solve_with_target(target_rate)
    
    if result:
        return result
    
    # If infeasible, use binary search to find max feasible rate
    low, high = 0.0, target_rate
    max_feasible = 0.0
    
    for _ in range(50):
        mid = (low + high) / 2
        test_result = try_solve_with_target(mid)
        
        if test_result:
            max_feasible = mid
            low = mid
        else:
            high = mid
        
        if high - low < 0.01:
            break
    
    # Identify bottlenecks
    bottlenecks = []
    if max_feasible < target_rate * 0.95:
        # Try to identify which constraint was hit
        for machine_type in sorted(machines.keys()):
            bottlenecks.append(f"{machine_type} cap")
        for item in sorted(raw_items):
            if item in raw_supply:
                bottlenecks.append(f"{item} supply")
    
    return {
        "status": "infeasible",
        "max_feasible_target_per_min": round(max_feasible, 2),
        "bottleneck_hint": bottlenecks[:2] if bottlenecks else ["unknown"]
    }


def solve_factory_simplex(data):
    """Solve factory optimization using Linear Programming (Simplex method via PuLP)."""
    
    machines = data["machines"]
    recipes = data["recipes"]
    modules = data.get("modules", {})
    limits = data["limits"]
    target = data["target"]
    
    raw_supply = limits["raw_supply_per_min"]
    max_machines = limits["max_machines"]
    target_item = target["item"]
    target_rate = target["rate_per_min"]
    
    # Helper functions for effective speeds and productivity
    def get_eff_crafts_per_min(recipe):
        machine_type = recipe["machine"]
        base_speed = machines[machine_type]["crafts_per_min"]
        time_s = recipe["time_s"]
        module = modules.get(machine_type, {})
        speed_mult = 1 + module.get("speed", 0)
        return (base_speed * speed_mult * 60) / time_s
    
    def get_prod_mult(recipe):
        machine_type = recipe["machine"]
        module = modules.get(machine_type, {})
        return 1 + module.get("prod", 0)
    
    # Identify all items
    all_items = set()
    produced_items = set()
    consumed_items = set()
    
    for recipe in recipes.values():
        all_items.update(recipe.get("in", {}).keys())
        all_items.update(recipe.get("out", {}).keys())
        produced_items.update(recipe.get("out", {}).keys())
        consumed_items.update(recipe.get("in", {}).keys())
    
    # Classify items:
    # - Raw items: not produced by any recipe
    # - Byproducts: produced but never consumed (and not the target)
    # - Intermediates: produced and consumed (cyclic items are intermediates)
    raw_items = {item for item in all_items if item not in produced_items}
    byproduct_items = {item for item in produced_items 
                       if item not in consumed_items and item != target_item}
    intermediate_items = (produced_items & consumed_items) - {target_item}
    
    def try_solve_lp(target_rate_scaled):
        """Try to solve using LP for a given target rate."""
        
        # Create LP problem
        prob = LpProblem("Factory_Optimization", LpMinimize)
        
        # Decision variables: crafts per minute for each recipe (sorted for determinism)
        x = {}
        for recipe_name in sorted(recipes.keys()):
            x[recipe_name] = LpVariable(f"crafts_{recipe_name}", lowBound=0)
        
        # Objective: minimize total machine usage
        machine_usage_terms = []
        for recipe_name in sorted(recipes.keys()):
            recipe = recipes[recipe_name]
            eff_crafts = get_eff_crafts_per_min(recipe)
            machine_usage_terms.append(x[recipe_name] / eff_crafts)
        
        prob += sum(machine_usage_terms), "Total_Machine_Usage"
        
        # Conservation constraints for each item
        for item in sorted(all_items):
            # Calculate net production (production - consumption)
            production = []
            consumption = []
            
            for recipe_name in sorted(recipes.keys()):
                recipe = recipes[recipe_name]
                
                # Production term
                if item in recipe.get("out", {}):
                    out_qty = recipe["out"][item]
                    prod_mult = get_prod_mult(recipe)
                    production.append(out_qty * prod_mult * x[recipe_name])
                
                # Consumption term
                if item in recipe.get("in", {}):
                    in_qty = recipe["in"][item]
                    consumption.append(in_qty * x[recipe_name])
            
            net_production = sum(production) - sum(consumption)
            
            # Apply constraint based on item type
            if item == target_item:
                # Target item: must produce exactly the target rate
                prob += net_production == target_rate_scaled, f"Target_{item}"
            
            elif item in intermediate_items:
                # Intermediate items (including cyclic): perfect balance (no accumulation)
                # For cycles (A→B→A), this ensures steady-state flow
                prob += net_production == 0, f"Balance_{item}"
            
            elif item in byproduct_items:
                # Byproducts: can produce surplus (not consumed anywhere)
                # Allow accumulation: net_production >= 0
                prob += net_production >= 0, f"Byproduct_{item}"
            
            elif item in raw_items:
                # Raw items: can only be consumed (net <= 0) and within supply
                prob += net_production <= 0, f"Raw_No_Production_{item}"
                if item in raw_supply:
                    prob += -net_production <= raw_supply[item], f"Raw_Supply_{item}"
        
        # Machine capacity constraints
        for machine_type in sorted(machines.keys()):
            machine_usage = []
            for recipe_name in sorted(recipes.keys()):
                recipe = recipes[recipe_name]
                if recipe["machine"] == machine_type:
                    eff_crafts = get_eff_crafts_per_min(recipe)
                    machine_usage.append(x[recipe_name] / eff_crafts)
            
            if machine_usage:
                total_usage = sum(machine_usage)
                max_cap = max_machines.get(machine_type, float('inf'))
                if max_cap < float('inf'):
                    prob += total_usage <= max_cap, f"Machine_Cap_{machine_type}"
        
        # Solve using CBC solver with deterministic settings
        solver = PULP_CBC_CMD(
            msg=0,  # Suppress output
            timeLimit=2,  # 2 second timeout
            threads=1,  # Single thread for determinism
            options=['randomS', '42']  # Fixed seed
        )
        
        prob.solve(solver)
        
        # Check if solution is optimal
        if LpStatus[prob.status] != "Optimal":
            return None
        
        # Extract results
        per_recipe_crafts = {}
        for recipe_name in sorted(recipes.keys()):
            crafts_value = x[recipe_name].varValue
            if crafts_value is not None and crafts_value > 1e-9:
                recipe = recipes[recipe_name]
                prod_mult = get_prod_mult(recipe)
                # Multiply by productivity to get actual output rate
                per_recipe_crafts[recipe_name] = crafts_value * prod_mult
        
        # Calculate machine counts
        machine_counts = {}
        for machine_type in sorted(machines.keys()):
            count = 0.0
            for recipe_name in sorted(recipes.keys()):
                recipe = recipes[recipe_name]
                if recipe["machine"] == machine_type:
                    crafts_value = x[recipe_name].varValue
                    if crafts_value is not None:
                        eff_crafts = get_eff_crafts_per_min(recipe)
                        count += crafts_value / eff_crafts
            if count > 1e-9:
                machine_counts[machine_type] = count
        
        # Calculate raw consumption
        raw_consumption = {}
        for item in sorted(raw_items):
            consumption = 0.0
            for recipe_name in sorted(recipes.keys()):
                recipe = recipes[recipe_name]
                if item in recipe.get("in", {}):
                    crafts_value = x[recipe_name].varValue
                    if crafts_value is not None:
                        consumption += recipe["in"][item] * crafts_value
            if consumption > 1e-9:
                raw_consumption[item] = consumption
        
        # Calculate byproduct surplus (if any)
        byproduct_surplus = {}
        for item in sorted(byproduct_items):
            production = 0.0
            consumption = 0.0
            for recipe_name in sorted(recipes.keys()):
                recipe = recipes[recipe_name]
                crafts_value = x[recipe_name].varValue
                if crafts_value is not None:
                    if item in recipe.get("out", {}):
                        out_qty = recipe["out"][item]
                        prod_mult = get_prod_mult(recipe)
                        production += out_qty * prod_mult * crafts_value
                    if item in recipe.get("in", {}):
                        in_qty = recipe["in"][item]
                        consumption += in_qty * crafts_value
            
            surplus = production - consumption
            if surplus > 1e-9:
                byproduct_surplus[item] = surplus
        
        result = {
            "status": "ok",
            "per_recipe_crafts_per_min": per_recipe_crafts,
            "per_machine_counts": machine_counts,
            "raw_consumption_per_min": raw_consumption
        }
        
        # Add byproduct surplus if any exist
        if byproduct_surplus:
            result["byproduct_surplus_per_min"] = byproduct_surplus
        
        return result
    
    # Try to solve with the target rate
    result = try_solve_lp(target_rate)
    
    if result:
        return result
    
    # If infeasible, use binary search to find max feasible rate
    low, high = 0.0, target_rate
    max_feasible = 0.0
    
    for _ in range(50):
        mid = (low + high) / 2
        test_result = try_solve_lp(mid)
        
        if test_result:
            max_feasible = mid
            low = mid
        else:
            high = mid
        
        if high - low < 0.01:
            break
    
    # Identify bottlenecks
    bottlenecks = []
    if max_feasible < target_rate * 0.95:
        for machine_type in sorted(machines.keys()):
            bottlenecks.append(f"{machine_type} cap")
        for item in sorted(raw_items):
            if item in raw_supply:
                bottlenecks.append(f"{item} supply")
    
    return {
        "status": "infeasible",
        "max_feasible_target_per_min": round(max_feasible, 2),
        "bottleneck_hint": bottlenecks[:2] if bottlenecks else ["unknown"]
    }


def main():
    # Read JSON from stdin
    data = json.load(sys.stdin)
    
    # Solve using simplex method (Linear Programming)
    result = solve_factory_simplex(data)
    
    # Write JSON to stdout
    json.dump(result, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main()

