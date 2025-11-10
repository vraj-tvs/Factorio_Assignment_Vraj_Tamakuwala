#!/usr/bin/env python3
"""
Factory input generator - creates various test cases for factory optimization.

Usage:
    python gen_factory.py simple
    python gen_factory.py complex
    python gen_factory.py infeasible
    python gen_factory.py cycles
    python gen_factory.py byproducts
    python gen_factory.py large
"""

import json
import sys
import random


def generate_simple():
    """Generate a simple feasible factory problem."""
    return {
        "machines": {
            "assembler": {"crafts_per_min": 30},
            "furnace": {"crafts_per_min": 60}
        },
        "recipes": {
            "iron_plate": {
                "machine": "furnace",
                "time_s": 3.2,
                "in": {"iron_ore": 1},
                "out": {"iron_plate": 1}
            },
            "gear": {
                "machine": "assembler",
                "time_s": 0.5,
                "in": {"iron_plate": 2},
                "out": {"gear": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"iron_ore": 2000},
            "max_machines": {"assembler": 50, "furnace": 50}
        },
        "target": {"item": "gear", "rate_per_min": 100}
    }


def generate_complex():
    """Generate a complex production chain with modules."""
    return {
        "machines": {
            "assembler_1": {"crafts_per_min": 30},
            "assembler_2": {"crafts_per_min": 45},
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
            },
            "red_circuit": {
                "machine": "assembler_2",
                "time_s": 6.0,
                "in": {"green_circuit": 2, "copper_plate": 2},
                "out": {"red_circuit": 1}
            },
            "blue_circuit": {
                "machine": "assembler_2",
                "time_s": 10.0,
                "in": {"red_circuit": 2, "green_circuit": 20},
                "out": {"blue_circuit": 1}
            }
        },
        "modules": {
            "assembler_1": {"prod": 0.1, "speed": 0.15},
            "assembler_2": {"prod": 0.2, "speed": 0.25},
            "chemical": {"prod": 0.2, "speed": 0.1}
        },
        "limits": {
            "raw_supply_per_min": {
                "iron_ore": 5000,
                "copper_ore": 10000
            },
            "max_machines": {
                "assembler_1": 100,
                "assembler_2": 50,
                "chemical": 200
            }
        },
        "target": {"item": "blue_circuit", "rate_per_min": 30}
    }


def generate_infeasible():
    """Generate an infeasible problem (insufficient resources)."""
    return {
        "machines": {
            "assembler": {"crafts_per_min": 100}
        },
        "recipes": {
            "product": {
                "machine": "assembler",
                "time_s": 1.0,
                "in": {"raw_material": 10},
                "out": {"product": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw_material": 500},
            "max_machines": {"assembler": 100}
        },
        "target": {"item": "product", "rate_per_min": 100}
    }


def generate_machine_limited():
    """Generate a problem limited by machine capacity."""
    return {
        "machines": {
            "slow_machine": {"crafts_per_min": 10}
        },
        "recipes": {
            "product": {
                "machine": "slow_machine",
                "time_s": 5.0,
                "in": {"raw": 1},
                "out": {"product": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 10000},
            "max_machines": {"slow_machine": 5}
        },
        "target": {"item": "product", "rate_per_min": 200}
    }


def generate_cycles():
    """Generate a problem with cyclic recipes."""
    return {
        "machines": {
            "assembler": {"crafts_per_min": 30},
            "refinery": {"crafts_per_min": 60}
        },
        "recipes": {
            "extract_oil": {
                "machine": "refinery",
                "time_s": 2.0,
                "in": {"crude_oil": 10},
                "out": {"petroleum": 5, "heavy_oil": 3}
            },
            "crack_heavy": {
                "machine": "refinery",
                "time_s": 1.5,
                "in": {"heavy_oil": 4},
                "out": {"petroleum": 3}
            },
            "make_plastic": {
                "machine": "assembler",
                "time_s": 1.0,
                "in": {"petroleum": 3},
                "out": {"plastic": 2}
            },
            "init_catalyst": {
                "machine": "assembler",
                "time_s": 10.0,
                "in": {"iron_ore": 10},
                "out": {"catalyst_a": 1}
            },
            "cycle_a_to_b": {
                "machine": "assembler",
                "time_s": 1.0,
                "in": {"catalyst_a": 1, "petroleum": 1},
                "out": {"catalyst_b": 1, "advanced_plastic": 5}
            },
            "cycle_b_to_a": {
                "machine": "assembler",
                "time_s": 1.0,
                "in": {"catalyst_b": 1},
                "out": {"catalyst_a": 1, "waste_gas": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {
                "crude_oil": 1000,
                "iron_ore": 100
            },
            "max_machines": {
                "assembler": 100,
                "refinery": 50
            }
        },
        "target": {"item": "advanced_plastic", "rate_per_min": 100}
    }


def main():
    generators = {
        "simple": ("Simple production chain", generate_simple),
        "complex": ("Complex multi-tier production", generate_complex),
        "infeasible": ("Infeasible problem", generate_infeasible),
        "machine-limited": ("Machine capacity limited", generate_machine_limited),
        "cycles": ("Production with cyclic recipes", generate_cycles),
    }
    
    if len(sys.argv) < 2:
        print("Factory Input Generator")
        print("=" * 60)
        print("\nUsage: python gen_factory.py <type>")
        print("\nAvailable types:")
        for key, (desc, _) in generators.items():
            print(f"  {key:15} - {desc}")
        print("\nExamples:")
        print("  python gen_factory.py simple > input.json")
        print("  python gen_factory.py cycles | python factory/main.py")
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

