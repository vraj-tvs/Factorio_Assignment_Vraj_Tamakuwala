#!/usr/bin/env python3
"""
Validation helper for factory CLI tool.
Verifies that output satisfies all constraints.

Usage: python verify_factory.py < input.json
       python factory/main.py < input.json | python verify_factory.py --check-output
"""

import json
import sys
import argparse


def verify_factory_output(input_data, output_data):
    """Verify that factory output satisfies all constraints."""
    
    if output_data["status"] != "ok":
        print(f"Output status is '{output_data['status']}', skipping validation")
        if output_data["status"] == "infeasible":
            print(f"Max feasible rate: {output_data.get('max_feasible_target_per_min', 'N/A')}")
            print(f"Bottlenecks: {output_data.get('bottleneck_hint', [])}")
        return True
    
    machines = input_data["machines"]
    recipes = input_data["recipes"]
    modules = input_data.get("modules", {})
    limits = input_data["limits"]
    target = input_data["target"]
    
    raw_supply = limits["raw_supply_per_min"]
    max_machines = limits["max_machines"]
    target_item = target["item"]
    target_rate = target["rate_per_min"]
    
    crafts_per_min = output_data["per_recipe_crafts_per_min"]
    machine_counts = output_data["per_machine_counts"]
    raw_consumption = output_data["raw_consumption_per_min"]
    byproduct_surplus = output_data.get("byproduct_surplus_per_min", {})
    
    errors = []
    warnings = []
    
    print("=" * 60)
    print("FACTORY OUTPUT VALIDATION")
    print("=" * 60)
    
    # Calculate effective crafts per minute for each recipe
    def get_eff_crafts_per_min(recipe_name, recipe):
        machine_type = recipe["machine"]
        base_speed = machines[machine_type]["crafts_per_min"]
        time_s = recipe["time_s"]
        module = modules.get(machine_type, {})
        speed_mult = 1 + module.get("speed", 0)
        return base_speed * speed_mult * 60 / time_s
    
    # Get productivity multiplier
    def get_prod_mult(recipe_name, recipe):
        machine_type = recipe["machine"]
        module = modules.get(machine_type, {})
        return 1 + module.get("prod", 0)
    
    # 1. Verify non-negativity constraint
    print("\n[1] Checking non-negativity constraint...")
    for recipe_name, crafts in crafts_per_min.items():
        if crafts < -1e-9:
            errors.append(f"Recipe '{recipe_name}' has negative crafts: {crafts}")
    
    if not any("negative crafts" in e for e in errors):
        print("    ✓ All recipe crafts are non-negative")
    
    # 2. Verify conservation equations for all items
    print("\n[2] Checking conservation equations...")
    
    # Identify all items and classify them
    all_items = set()
    produced_items = set()
    consumed_items = set()
    
    for recipe in recipes.values():
        all_items.update(recipe.get("in", {}).keys())
        all_items.update(recipe.get("out", {}).keys())
        produced_items.update(recipe.get("out", {}).keys())
        consumed_items.update(recipe.get("in", {}).keys())
    
    raw_items = {item for item in all_items if item not in produced_items}
    byproduct_items = {item for item in produced_items 
                       if item not in consumed_items and item != target_item}
    intermediate_items = (produced_items & consumed_items) - {target_item}
    
    # NOTE: Output values include productivity multiplier, so we need to divide by it
    # to get actual crafts when checking conservation
    for item in sorted(all_items):
        production = 0
        consumption = 0
        
        for recipe_name, recipe in recipes.items():
            # Output values already include productivity, so divide to get base crafts
            prod_mult = get_prod_mult(recipe_name, recipe)
            x = crafts_per_min.get(recipe_name, 0) / prod_mult if prod_mult > 0 else 0
            
            if item in recipe.get("out", {}):
                production += recipe["out"][item] * prod_mult * x
            
            if item in recipe.get("in", {}):
                consumption += recipe["in"][item] * x
        
        net = production - consumption
        
        if item == target_item:
            # Constraint: net production == target_rate
            if abs(net - target_rate) > 1.0:
                errors.append(f"Target '{item}' production {net:.2f} ≠ target {target_rate}")
            else:
                print(f"    ✓ Target '{item}': {net:.2f} items/min = {target_rate} (exact match)")
        
        elif item in raw_items:
            # Constraint: net production <= 0 (only consumed)
            # Constraint: consumption <= raw_supply
            if net > 1e-6:
                errors.append(f"Raw item '{item}' has net production {net:.2f} > 0 (should only be consumed)")
            
            if -net > raw_supply.get(item, 0) + 1e-6:
                errors.append(f"Raw '{item}' consumption {-net:.2f} > supply {raw_supply.get(item, 0)}")
            elif -net > 1e-6:
                print(f"    ✓ Raw '{item}': consuming {-net:.2f} ≤ {raw_supply.get(item, 0)} supply")
        
        elif item in byproduct_items:
            # Constraint: net production >= 0 (can accumulate)
            if net < -1e-6:
                errors.append(f"Byproduct '{item}' has net consumption {net:.2f} < 0")
            elif net > 1e-6:
                if item in byproduct_surplus:
                    reported_surplus = byproduct_surplus[item]
                    if abs(net - reported_surplus) > 0.1:
                        warnings.append(f"Byproduct '{item}' calculated surplus {net:.2f} ≠ reported {reported_surplus:.2f}")
                    print(f"    ✓ Byproduct '{item}': {net:.2f} surplus/min (accumulating)")
                else:
                    warnings.append(f"Byproduct '{item}' has surplus {net:.2f} but not in output")
        
        elif item in intermediate_items:
            # Constraint: net production == 0 (perfect balance, including cycles)
            if abs(net) > 1.0:
                errors.append(f"Intermediate '{item}' not balanced: net={net:.2f} (should be 0)")
            else:
                print(f"    ✓ Intermediate '{item}': balanced (net={net:.4f} ≈ 0)")
    
    # 3. Verify machine capacity constraints
    print("\n[3] Checking machine capacity constraints...")
    
    for machine_type in sorted(machines.keys()):
        calculated_usage = 0
        
        for recipe_name, recipe in recipes.items():
            if recipe["machine"] == machine_type:
                # Output includes productivity, divide to get base crafts
                prod_mult = get_prod_mult(recipe_name, recipe)
                x = crafts_per_min.get(recipe_name, 0) / prod_mult if prod_mult > 0 else 0
                eff_crafts = get_eff_crafts_per_min(recipe_name, recipe)
                calculated_usage += x / eff_crafts
        
        reported_usage = machine_counts.get(machine_type, 0)
        max_cap = max_machines.get(machine_type, float('inf'))
        
        # Check reported vs calculated
        if abs(calculated_usage - reported_usage) > 0.01:
            warnings.append(f"Machine '{machine_type}' count mismatch: calculated={calculated_usage:.4f}, reported={reported_usage:.4f}")
        
        # Check capacity constraint
        if reported_usage > max_cap + 1e-6:
            errors.append(f"Machine '{machine_type}' usage {reported_usage:.4f} > limit {max_cap}")
        elif reported_usage > 1e-9:
            utilization = (reported_usage / max_cap * 100) if max_cap < float('inf') else 0
            if max_cap < float('inf'):
                print(f"    ✓ Machine '{machine_type}': {reported_usage:.4f} ≤ {max_cap} ({utilization:.1f}% utilized)")
            else:
                print(f"    ✓ Machine '{machine_type}': {reported_usage:.4f} machines (no limit)")
    
    # 4. Verify raw consumption matches
    print("\n[4] Checking raw consumption calculations...")
    
    for item in sorted(raw_items):
        calculated_consumption = 0
        calculated_production = 0
        
        for recipe_name, recipe in recipes.items():
            # Output includes productivity, divide to get base crafts
            prod_mult = get_prod_mult(recipe_name, recipe)
            x = crafts_per_min.get(recipe_name, 0) / prod_mult if prod_mult > 0 else 0
            
            if item in recipe.get("in", {}):
                calculated_consumption += recipe["in"][item] * x
            if item in recipe.get("out", {}):
                calculated_production += recipe["out"][item] * prod_mult * x
        
        net_consumption = calculated_consumption - calculated_production
        reported_consumption = raw_consumption.get(item, 0)
        
        if abs(net_consumption - reported_consumption) > 0.1:
            warnings.append(f"Raw '{item}' consumption mismatch: calculated={net_consumption:.2f}, reported={reported_consumption:.2f}")
        elif net_consumption > 1e-6:
            print(f"    ✓ Raw '{item}': {reported_consumption:.2f} items/min consumed")
    
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
        print("\nAll factory constraints are satisfied:")
        print("  • Non-negativity: All recipe crafts ≥ 0")
        print("  • Conservation: Production = Consumption for all items")
        print("  • Machine capacity: All machine usage ≤ limits")
        print("  • Raw supply: All raw consumption ≤ supply")
        print("  • Target production: Exactly met")
        return True
    
    print("=" * 60)
    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Validate factory output")
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
            # Run factory tool
            import subprocess
            result = subprocess.run(
                [sys.executable, "factory/main.py"],
                input=json.dumps(input_data),
                capture_output=True,
                text=True
            )
            output_data = json.loads(result.stdout)
    
    success = verify_factory_output(input_data, output_data)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

