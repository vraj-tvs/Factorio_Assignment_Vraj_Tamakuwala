#!/usr/bin/env python3
"""
Run sample test cases for both factory and belts CLI tools.

Usage:
    python run_samples.py
    python run_samples.py "python factory/main.py" "python belts/main.py"
"""

import json
import subprocess
import sys
import time
from pathlib import Path


def run_tool(cmd, input_data, timeout=2):
    """Run a CLI tool with given input."""
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd.split(),
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "elapsed": elapsed
            }
        
        output = json.loads(result.stdout)
        
        return {
            "success": True,
            "output": output,
            "elapsed": elapsed
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Timeout (>{timeout}s)",
            "elapsed": timeout
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON output: {e}",
            "elapsed": time.time() - start_time
        }


def test_factory_samples(factory_cmd):
    """Run factory sample tests."""
    print("\n" + "="*60)
    print("FACTORY TESTS")
    print("="*60)
    
    samples = []
    
    # Sample 1: Basic feasible case
    samples.append({
        "name": "Basic feasible production",
        "input": {
            "machines": {
                "assembler_1": {"crafts_per_min": 30},
                "chemical": {"crafts_per_min": 60}
            },
            "recipes": {
                "iron_plate": {
                    "machine": "chemical",
                    "time_s": 3.2,
                    "in": {"iron_ore": 1},
                    "out": {"iron_plate": 1}
                },
                "copper_plate": {
                    "machine": "chemical",
                    "time_s": 3.2,
                    "in": {"copper_ore": 1},
                    "out": {"copper_plate": 1}
                },
                "green_circuit": {
                    "machine": "assembler_1",
                    "time_s": 0.5,
                    "in": {"iron_plate": 1, "copper_plate": 3},
                    "out": {"green_circuit": 1}
                }
            },
            "modules": {
                "assembler_1": {"prod": 0.1, "speed": 0.15},
                "chemical": {"prod": 0.2, "speed": 0.1}
            },
            "limits": {
                "raw_supply_per_min": {"iron_ore": 5000, "copper_ore": 5000},
                "max_machines": {"assembler_1": 300, "chemical": 300}
            },
            "target": {"item": "green_circuit", "rate_per_min": 1800}
        }
    })
    
    # Sample 2: Infeasible case
    samples.append({
        "name": "Infeasible (insufficient raw)",
        "input": {
            "machines": {"assembler": {"crafts_per_min": 100}},
            "recipes": {
                "product": {
                    "machine": "assembler",
                    "time_s": 1.0,
                    "in": {"raw": 10},
                    "out": {"product": 1}
                }
            },
            "modules": {},
            "limits": {
                "raw_supply_per_min": {"raw": 500},
                "max_machines": {"assembler": 100}
            },
            "target": {"item": "product", "rate_per_min": 100}
        }
    })
    
    # Run samples
    for i, sample in enumerate(samples, 1):
        print(f"\n[{i}/{len(samples)}] {sample['name']}")
        print("-" * 60)
        
        result = run_tool(factory_cmd, sample["input"])
        
        if result["success"]:
            print(f"✓ Status: {result['output']['status']}")
            print(f"✓ Time: {result['elapsed']:.3f}s")
            
            if result['output']['status'] == 'ok':
                print(f"  Recipes used: {len(result['output']['per_recipe_crafts_per_min'])}")
                print(f"  Machines: {result['output']['per_machine_counts']}")
            else:
                print(f"  Max feasible: {result['output'].get('max_feasible_target_per_min', 'N/A')}")
        else:
            print(f"✗ FAILED: {result['error']}")
            print(f"  Time: {result['elapsed']:.3f}s")


def test_belts_samples(belts_cmd):
    """Run belts sample tests."""
    print("\n" + "="*60)
    print("BELTS TESTS")
    print("="*60)
    
    samples = []
    
    # Sample 1: Simple flow
    samples.append({
        "name": "Simple source to sink",
        "input": {
            "edges": [
                {"from": "s1", "to": "sink", "lo": 0, "hi": 1000}
            ],
            "sources": [{"node": "s1", "supply": 500}],
            "sink": "sink"
        }
    })
    
    # Sample 2: Multi-path network (spec example)
    samples.append({
        "name": "Multi-source with parallel paths",
        "input": {
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
    })
    
    # Run samples
    for i, sample in enumerate(samples, 1):
        print(f"\n[{i}/{len(samples)}] {sample['name']}")
        print("-" * 60)
        
        result = run_tool(belts_cmd, sample["input"])
        
        if result["success"]:
            print(f"✓ Status: {result['output']['status']}")
            print(f"✓ Time: {result['elapsed']:.3f}s")
            
            if result['output']['status'] == 'ok':
                print(f"  Max flow: {result['output']['max_flow_per_min']}")
                print(f"  Edges with flow: {len(result['output']['flows'])}")
            else:
                print(f"  Deficit: {result['output']['deficit']['demand_balance']}")
        else:
            print(f"✗ FAILED: {result['error']}")
            print(f"  Time: {result['elapsed']:.3f}s")


def main():
    if len(sys.argv) > 2:
        factory_cmd = sys.argv[1]
        belts_cmd = sys.argv[2]
    else:
        factory_cmd = f"{sys.executable} factory/main.py"
        belts_cmd = f"{sys.executable} belts/main.py"
    
    print("Running sample tests...")
    print(f"Factory command: {factory_cmd}")
    print(f"Belts command: {belts_cmd}")
    
    test_factory_samples(factory_cmd)
    test_belts_samples(belts_cmd)
    
    print("\n" + "="*60)
    print("SAMPLE TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()

