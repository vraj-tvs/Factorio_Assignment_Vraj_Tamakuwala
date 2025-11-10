#!/usr/bin/env python3
"""
Unit tests for the factory CLI tool.
Run with: pytest tests/test_factory.py -v
Or: python tests/test_factory.py
"""

import json
import subprocess
import sys
import os


def run_factory(input_data):
    """Run factory tool with given input, return parsed output."""
    cmd = [sys.executable, "factory/main.py"]
    result = subprocess.run(
        cmd,
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        timeout=3
    )
    
    if result.returncode != 0:
        raise Exception(f"Factory failed: {result.stderr}")
    
    return json.loads(result.stdout)


def test_basic_feasible():
    """Test basic feasible case from spec."""
    input_data = {
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
    
    result = run_factory(input_data)
    
    assert result["status"] == "ok"
    assert "per_recipe_crafts_per_min" in result
    assert "per_machine_counts" in result
    assert "raw_consumption_per_min" in result
    
    # Check that green_circuit is produced at the target rate
    # With 10% productivity: 1636.36 crafts * 1.1 = 1800 items/min
    green_crafts = result["per_recipe_crafts_per_min"]["green_circuit"]
    assert abs(green_crafts - 1800) < 0.1
    
    print("✓ Basic feasible test passed")


def test_infeasible_raw_supply():
    """Test infeasibility due to insufficient raw materials."""
    input_data = {
        "machines": {
            "assembler": {"crafts_per_min": 100}
        },
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
            "raw_supply_per_min": {"raw": 500},  # Not enough!
            "max_machines": {"assembler": 100}
        },
        "target": {"item": "product", "rate_per_min": 100}  # Needs 1000 raw/min
    }
    
    result = run_factory(input_data)
    
    assert result["status"] == "infeasible"
    assert "max_feasible_target_per_min" in result
    assert result["max_feasible_target_per_min"] < 100
    
    print("✓ Infeasible raw supply test passed")


def test_infeasible_machine_cap():
    """Test infeasibility due to insufficient machines."""
    input_data = {
        "machines": {
            "assembler": {"crafts_per_min": 10}
        },
        "recipes": {
            "product": {
                "machine": "assembler",
                "time_s": 6.0,  # 10 crafts/min * 60/6 = 100 crafts/min per machine
                "in": {"raw": 1},
                "out": {"product": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 10000},
            "max_machines": {"assembler": 5}  # Can only do 500 crafts/min max
        },
        "target": {"item": "product", "rate_per_min": 1000}  # Needs 10 machines
    }
    
    result = run_factory(input_data)
    
    assert result["status"] == "infeasible"
    assert "max_feasible_target_per_min" in result
    assert result["max_feasible_target_per_min"] <= 500
    
    print("✓ Infeasible machine cap test passed")


def test_no_modules():
    """Test case without any modules."""
    input_data = {
        "machines": {
            "assembler": {"crafts_per_min": 60}
        },
        "recipes": {
            "product": {
                "machine": "assembler",
                "time_s": 2.0,
                "in": {"raw": 1},
                "out": {"product": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 5000},
            "max_machines": {"assembler": 100}
        },
        "target": {"item": "product", "rate_per_min": 900}
    }
    
    result = run_factory(input_data)
    
    assert result["status"] == "ok"
    # 60 crafts/min * 60 / 2.0 = 1800 crafts/min per machine
    # Need 900 crafts/min -> 0.5 machines
    machines_used = result["per_machine_counts"]["assembler"]
    assert abs(machines_used - 0.5) < 0.01
    
    print("✓ No modules test passed")


def test_chain_production():
    """Test production chain with intermediates."""
    input_data = {
        "machines": {
            "machine_a": {"crafts_per_min": 60},
            "machine_b": {"crafts_per_min": 30}
        },
        "recipes": {
            "step1": {
                "machine": "machine_a",
                "time_s": 1.0,
                "in": {"raw": 2},
                "out": {"intermediate": 1}
            },
            "step2": {
                "machine": "machine_b",
                "time_s": 2.0,
                "in": {"intermediate": 3},
                "out": {"final": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 10000},
            "max_machines": {"machine_a": 100, "machine_b": 100}
        },
        "target": {"item": "final", "rate_per_min": 300}
    }
    
    result = run_factory(input_data)
    
    assert result["status"] == "ok"
    
    # Need 300 final/min
    # step2: 300 final needs 900 intermediate
    # step1: 900 intermediate needs 1800 raw
    raw_used = result["raw_consumption_per_min"]["raw"]
    assert abs(raw_used - 1800) < 1
    
    print("✓ Chain production test passed")


def test_determinism():
    """Test that multiple runs produce identical output."""
    input_data = {
        "machines": {
            "m1": {"crafts_per_min": 30}
        },
        "recipes": {
            "r1": {
                "machine": "m1",
                "time_s": 1.0,
                "in": {"raw": 1},
                "out": {"product": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 5000},
            "max_machines": {"m1": 100}
        },
        "target": {"item": "product", "rate_per_min": 500}
    }
    
    results = [run_factory(input_data) for _ in range(3)]
    
    # All results should be identical
    for i in range(1, len(results)):
        assert json.dumps(results[0], sort_keys=True) == json.dumps(results[i], sort_keys=True)
    
    print("✓ Determinism test passed")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_basic_feasible,
        test_infeasible_raw_supply,
        test_infeasible_machine_cap,
        test_no_modules,
        test_chain_production,
        test_determinism
    ]
    
    print("Running factory tests...\n")
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

