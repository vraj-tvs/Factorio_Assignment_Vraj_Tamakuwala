# ERP.AI Engineering Assessment - Implementation

## Overview

This repository contains two command-line tools for optimization problems:

1. **Factory**: Steady-state production optimization with Linear Programming
2. **Belts**: Max-flow problem with lower bounds and node capacity constraints

Both tools read JSON from stdin, write JSON to stdout, produce deterministic results, and complete within 2 seconds.

---

## Factory Tool - Design Choices

### Problem Modeling

The factory steady-state problem is formulated as a **Linear Program (LP)** using the PuLP library with the CBC solver.

#### Item Balance and Conservation Equations

**Conservation Law**: For each item `i`, the net production must match requirements:

```
Σ_r [out_r[i] × (1 + prod_m) × x_r] - Σ_r [in_r[i] × x_r] = b[i]
```

Where:

- `x_r` = crafts per minute for recipe r (decision variables)
- `out_r[i]` = base output of item i from recipe r
- `in_r[i]` = input required of item i for recipe r
- `prod_m` = productivity multiplier for machine type m
- `b[i]` = required net production/consumption for item i

**Item Classification**:

- **Target item**: `b[target] = target_rate` (exact match required)
- **Intermediate items**: `b[i] = 0` (perfect balance, no accumulation, includes cyclic items)
- **Byproduct items**: `b[i] ≥ 0` (can accumulate, produced but not consumed)
- **Raw materials**: `b[i] ≤ 0` and `|b[i]| ≤ supply_cap[i]` (net consumption within limits)

Items are classified programmatically:

```python
produced_items = {i for r in recipes for i in r.out}
consumed_items = {i for r in recipes for i in r.in}
raw_items = all_items - produced_items
byproduct_items = produced_items - consumed_items - {target_item}
intermediate_items = (produced_items ∩ consumed_items) - {target_item}
```

#### Raw Consumption Constraints

Raw materials have two constraints:

1. **No Creation**: `net_production[i] ≤ 0`

   - Raw items cannot be produced by recipes
   - Only consumption is allowed

2. **Supply Cap**: `consumption[i] ≤ raw_supply_per_min[i]`
   - Total consumption cannot exceed available supply
   - Implemented as: `-net_production[i] ≤ supply_cap[i]`


#### Machine Capacity Constraints

For each machine type `m`:

```
Σ_{r uses m} (x_r / eff_crafts_per_min[r]) ≤ max_machines[m]
```

Where `machines_used_by_recipe[r] = x_r / eff_crafts_per_min[r]`

This ensures total fractional machine usage doesn't exceed available capacity.

### Module Application (Per-Machine-Type)

Modules (speed and productivity bonuses) apply uniformly to all recipes using the same machine type.

#### Speed Multiplier

Affects how fast recipes complete:

```python
eff_crafts_per_min(r) = base_speed × (1 + speed_mult) × 60 / time_s
```

**Example**: 
- Base speed: 30 crafts/min
- Speed module: +15% (speed_mult = 0.15)
- Recipe time: 0.5s
- Result: `30 × 1.15 × 60 / 0.5 = 4140 crafts/min per machine`

#### Productivity Multiplier

Affects only outputs (not inputs):

```python
effective_output[i] = base_output[i] × (1 + prod_mult)
```

**Example**:
- Base output: 1 green_circuit per craft
- Productivity module: +10% (prod_mult = 0.1)
- Effective output: 1.1 green_circuits per craft

**Key Insight**: Productivity reduces crafts needed:
- To produce 1800 items/min with 1.1× productivity
- Requires only 1800/1.1 = 1636.36 crafts/min

---

## Factory — Modeling choices

- Item balances / conservation equations

  - For each item i: Σ_r [effective_out_r[i] × x_r] - Σ_r [in_r[i] × x_r] = b[i]
  - Classification: target (b[target]=target_rate), intermediates (b=0), byproducts (b≥0), raw materials (b≤0 and bounded by supply cap).

- Raw consumption and machine capacity

  - Raw items: net_production ≤ 0 and -net_production ≤ supply_cap.
  - Machine capacity per type m: Σ\_{r uses m} (x_r / eff_crafts_per_min[r]) ≤ max_machines[m].

- Module application (per-machine-type)

  - Speed modules scale craft rate: eff_crafts_per_min = base_speed × (1+speed_mult) × 60 / time_s.
  - Productivity modules scale outputs only: effective_output = base_output × (1+prod_mult).

- Handling cycles, byproducts, self-contained recipes

  - Cyclic intermediates: set b[i]=0; conservation enforces steady-state circulation automatically.
  - Byproducts (produced but never consumed): allow net_production ≥ 0 so surplus accumulates; report byproduct_surplus_per_min.
  - Self-contained recipes (consume and produce same items): treated as cyclic/intermediate — LP chooses a non-zero rate only if beneficial.

- Tie-breaking and objective

  - Primary objective: meet target exactly. Secondary: minimize total machines used via objective minimize Σ_r (x_r / eff_crafts_per_min[r]).
  - Determinism: sort recipes/items lexicographically when building constraints; fix solver seed and run single-threaded.

- Infeasibility detection & reporting
  - Use LP's infeasibility detection (CBC Simplex Phase I). If infeasible, binary search target in [0, target] to find max feasible rate (precision via fixed iterations). Report max_feasible_target_per_min and conservative bottleneck hints (machine caps / raw supplies near limits).

--- 

## Belts — Modeling choices

- Max-flow with lower bounds (transformation)

  - Convert lo≤f≤hi to capacities hi-lo; track node imbalances: imbalance[u]-=lo, imbalance[v]+=lo.
  - Solve circulation/feasibility then reconstruct f = f' + lo.

- Order of operations

  1. Node-splitting for node capacity constraints
  2. Lower-bound transform (imbalance calculation)
  3. Feasibility check via auxiliary super-source/sink (s* / t*)
  4. Main flow computation (virtual source → sink)
  5. Reconstruct original flows

- Node-splitting for capacity constraints

  - Replace node v with v_in → v_out edge of capacity cap[v]; redirect incoming → v_in and outgoing from v_out. Do not split sources/sink.

- Feasibility check strategy

  - Build s*/t* with edges for node demands/supplies and run max-flow; if all demands satisfied, lower bounds feasible; else report infeasible early.

- Infeasibility certificates (min-cut)
  - After max-flow, find reachable set in residual graph (BFS on residual edges with capacity > ε). Certificate includes cut_reachable, demand_balance (unsatisfied flow), tight_nodes (nodes at cap), and tight_edges crossing the cut.

--- 

## Numeric approach and solver choices

- Tolerances

  - Use tight tolerances to avoid floating-point artifacts (example ε = 1e-9 for conservation and capacity checks).

- Solvers / algorithms

  - Factory: LP (PuLP + CBC) using simplex (deterministic with fixed seed). Chosen for natural formulation, correctness, and built-in infeasibility detection.
  - Belts: Hand-implemented deterministic Edmonds–Karp (BFS). Chosen for clarity, determinism, and sufficient performance.

- Tie-breaking for determinism
  - Sort nodes, edges, recipes lexicographically when iterating and building constraints or BFS neighbor lists. Use fixed solver options and single-threading to get bit-identical outputs.

--- 

## Failure modes & edge cases (what to watch for)

- Factory

  - Cycles in recipes: handled by b=0 balances; LP finds steady-state flows or zero rates if non-beneficial.
  - Infeasible raw supply or machine counts: LP reports infeasible; binary search finds max feasible target and bottleneck hints.
  - Degenerate / redundant recipes: LP sets non-useful recipes to zero; objective minimizes machines so efficient recipes preferred; tie-break via lexicographic order.

- Belts
  - Disconnected components: flow from unreachable sources is zero; min-cut shows disconnected supplies.
  - Unsatisfiable lower bounds or node-cap conflicts: detected in Phase 1 feasibility check; report deficit and certificate indicating bottleneck nodes/edges.

--- 

## Minimal implementation & testing notes

- Factory: `factory/main.py` (LP with PuLP + CBC). Keep deterministic seed and sort inputs.
- Belts: `belts/main.py` (Edmonds–Karp + transforms). Use sorted neighbor lists.
- Tests: check conservation, capacity, and deterministic outputs; when infeasible, validate returned max_feasible_target_per_min and certificate fields.

---

