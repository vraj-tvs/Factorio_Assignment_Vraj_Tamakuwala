# Run Instructions

## Setup

### Create Virtual Environment and Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### Requirements

- Python 3.7+
- PuLP >= 2.7.0 (for factory tool)
- Belts tool has no external dependencies

## Running the CLI Tools

### Factory Tool

Reads JSON from stdin, writes JSON to stdout.

```bash
# Basic usage
python factory/main.py < sample_factory_input.json > factory_output.json

# Pretty-print output
python factory/main.py < sample_factory_input.json | python -m json.tool

# With virtual environment activated
source venv/bin/activate
python factory/main.py < input.json > output.json
```

### Belts Tool

Reads JSON from stdin, writes JSON to stdout.

```bash
# Basic usage
python belts/main.py < sample_belts_input.json > belts_output.json

# Pretty-print output
python belts/main.py < sample_belts_input.json | python -m json.tool

# With virtual environment activated
source venv/bin/activate
python belts/main.py < input.json > output.json
```

## Input Generators

Generate various test cases for both tools:

### Factory Input Generator

```bash
# See available types
python gen_factory.py

# Generate specific types
python gen_factory.py simple > input.json
python gen_factory.py complex > input.json
python gen_factory.py cycles > input.json
python gen_factory.py infeasible > input.json
python gen_factory.py machine-limited > input.json

# Pipe directly to solver
python gen_factory.py cycles | python factory/main.py | python -m json.tool
```

**Available types**:
- `simple` - Simple production chain
- `complex` - Complex multi-tier production
- `infeasible` - Infeasible problem (insufficient resources)
- `machine-limited` - Machine capacity limited
- `cycles` - Production with cyclic recipes

### Belts Input Generator

```bash
# See available types
python gen_belts.py

# Generate specific types
python gen_belts.py simple > input.json
python gen_belts.py parallel > input.json
python gen_belts.py grid > input.json
python gen_belts.py bottleneck > input.json

# Pipe directly to solver
python gen_belts.py parallel | python belts/main.py | python -m json.tool
```

**Available types**:
- `simple` - Simple single path
- `parallel` - Parallel paths network
- `bottleneck` - Network with bottleneck
- `lower-bounds` - Network with lower bound constraints
- `node-caps` - Network with node capacity constraints
- `grid` - Grid network (3x3)
- `large` - Large random network (20 nodes)
- `infeasible` - Infeasible problem
- `balanced` - Perfectly balanced network

## Sample Inputs

Sample input files are provided:
- `sample_factory_input.json` - Factory optimization example
- `sample_belts_input.json` - Belt flow network example
- Or generate custom inputs using `gen_factory.py` and `gen_belts.py`

## Expected Behavior

- Both tools read JSON from stdin
- Both tools write a single JSON object to stdout
- No extra prints, logs, or debug output
- Deterministic results for identical inputs
- Complete within ≤ 2 seconds per case

## Validation Helpers

Validate that outputs satisfy all constraints:

### Factory Validation

```bash
# Validate with input and output files
python verify_factory.py --input sample_factory_input.json --output factory_output.json

# Run solver and validate in pipeline
python verify_factory.py --input sample_factory_input.json

# Generate, solve, and validate
python gen_factory.py cycles | python verify_factory.py --input <(python gen_factory.py cycles)
```

### Belts Validation

```bash
# Validate with input and output files
python verify_belts.py --input sample_belts_input.json --output belts_output.json

# Run solver and validate in pipeline
python verify_belts.py --input sample_belts_input.json

# Generate, solve, and validate
python gen_belts.py parallel | python verify_belts.py --input <(python gen_belts.py parallel)
```

**What validation checks**:
- **Factory**: Non-negativity, conservation equations, machine capacity, raw supply limits, target production
- **Belts**: Edge capacities (lo ≤ flow ≤ hi), flow conservation, node capacities, non-negativity, total flow

## Testing

### Quick Test

```bash
# Test factory
source venv/bin/activate
python factory/main.py < sample_factory_input.json | python -m json.tool

# Test belts
python belts/main.py < sample_belts_input.json | python -m json.tool
```

### Run Sample Tests

Run multiple test cases for both tools:

```bash
# Activate virtual environment first
source venv/bin/activate

# Run sample tests with default commands
python run_samples.py

# Run sample tests with custom commands
python run_samples.py "python factory/main.py" "python belts/main.py"
```

This will test:
- Factory: Basic feasible case, infeasible case
- Belts: Simple flow, multi-path network

### Run Pytest

Run comprehensive test suite:

```bash
# Activate virtual environment first
source venv/bin/activate

# Run all tests
FACTORY_CMD="python factory/main.py" BELTS_CMD="python belts/main.py" pytest

# Run tests quietly
FACTORY_CMD="python factory/main.py" BELTS_CMD="python belts/main.py" pytest -q

# Run specific test file
FACTORY_CMD="python factory/main.py" pytest tests/test_factory.py -v

# Run with verbose output
FACTORY_CMD="python factory/main.py" BELTS_CMD="python belts/main.py" pytest -v
```

### Expected Outputs

**Factory** (sample_factory_input.json):
```json
{
  "status": "ok",
  "per_recipe_crafts_per_min": {
    "copper_plate": 4090.91,
    "green_circuit": 1636.36,
    "iron_plate": 1363.64
  },
  "per_machine_counts": {
    "assembler_1": 0.395,
    "chemical": 4.408
  },
  "raw_consumption_per_min": {
    "copper_ore": 4090.91,
    "iron_ore": 1363.64
  }
}
```

**Belts** (sample_belts_input.json):
```json
{
  "status": "ok",
  "max_flow_per_min": 1500.0,
  "flows": [
    {"from": "s1", "to": "a", "flow": 900.0},
    {"from": "s2", "to": "a", "flow": 600.0},
    {"from": "a", "to": "b", "flow": 900.0},
    {"from": "a", "to": "c", "flow": 600.0},
    {"from": "b", "to": "sink", "flow": 900.0},
    {"from": "c", "to": "sink", "flow": 600.0}
  ]
}
```

## Complete Workflow Example

Here's a complete example using all tools:

```bash
# Setup
source venv/bin/activate

# Generate a test case
python gen_factory.py cycles > test_input.json

# Solve it
python factory/main.py < test_input.json > test_output.json

# Pretty-print the output
cat test_output.json | python -m json.tool

# Validate the solution
python verify_factory.py --input test_input.json --output test_output.json

# Or do it all in a pipeline
python gen_factory.py cycles | \
  tee test_input.json | \
  python factory/main.py | \
  tee test_output.json | \
  python -m json.tool
```

## Available Tools

| Tool | Purpose | Dependencies |
|------|---------|--------------|
| `factory/main.py` | Solve factory optimization | PuLP >= 2.7.0 |
| `belts/main.py` | Solve max-flow problems | None |
| `gen_factory.py` | Generate factory test cases | None |
| `gen_belts.py` | Generate belts test cases | None |
| `verify_factory.py` | Validate factory solutions | None |
| `verify_belts.py` | Validate belts solutions | None |
| `run_samples.py` | Run sample test suite | None |

## Environment

- **Python**: 3.7 or higher
- **Dependencies**: 
  - `pulp >= 2.7.0` (for factory tool only)
  - No dependencies for belts tool
  - No dependencies for generators and validators
- **Installation**: `pip install -r requirements.txt`

## Troubleshooting

### "ModuleNotFoundError: No module named 'pulp'"

Make sure you've activated the virtual environment and installed dependencies:
```bash
source venv/bin/activate
pip install -r requirements.txt
# OR
pip install pulp
```

### Validation Helpers Show Errors

If `verify_factory.py` or `verify_belts.py` report constraint violations:
- Check that you're using the correct input file
- Ensure output is valid JSON
- Review the specific constraints that failed
- The validators show which constraint was violated and the values

Example validation error:
```
❌ VALIDATION FAILED
Constraint Violations:
  1. ✗ Target 'green_circuit' production 1500.00 ≠ target 1800
```

### Slow Performance

Both tools should complete in < 2 seconds. If they're taking longer:
- Check input size (number of recipes/edges)
- Ensure you're not running in debug mode
- Check that PuLP CBC solver is installed correctly
- For factory: Large problems (100+ recipes) may take longer
- For belts: Edmonds-Karp is O(V×E²), very large graphs may be slow

### Non-Deterministic Output

Both tools are designed to produce deterministic output. If you see variations:
- Check Python version (should be 3.7+)
- Verify no external randomness in input
- Ensure same solver versions (PuLP >= 2.7.0)
- Factory uses fixed seed: `options=['randomS', '42']`
- Belts uses sorted BFS exploration

### Input Generator Issues

If generators fail or produce invalid input:
- Check that you spelled the type correctly (case-sensitive)
- Run without arguments to see available types
- Generators use random for some types, but with fixed seed

### Pytest Failures

If pytest tests fail:
- Ensure environment variables are set: `FACTORY_CMD` and `BELTS_CMD`
- Activate virtual environment before running tests
- Check that all tools are in correct locations
- Run with `-v` flag for detailed output

```bash
source venv/bin/activate
FACTORY_CMD="python factory/main.py" BELTS_CMD="python belts/main.py" pytest -v
```

## Quick Reference

```bash
# Setup (one time)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate input
python gen_factory.py <type>  # or gen_belts.py

# Solve
python factory/main.py < input.json  # or belts/main.py

# Validate
python verify_factory.py --input input.json --output output.json

# Run tests
python run_samples.py
FACTORY_CMD="python factory/main.py" BELTS_CMD="python belts/main.py" pytest -q
```

