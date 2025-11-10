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

$$\sum_{r} [out\_r[i] * (1 + prod\_m) * x\_r] - \sum_{r} [in\_r[i] * x\_r] = b[i]$$

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

$$eff\_crafts\_per\_min(r) = \frac{base\_speed * (1 + speed\_mult) * 60}{time\_s}$$

**Example**:

- Base speed: `30 crafts/min`
- Speed module: `+15\% (speed_mult = 0.15)`
- Recipe time: `0.5s`
- Result: `30 × 1.15 × 60 / 0.5 = 4140 crafts/min per machine`

#### Productivity Multiplier

Affects only outputs (not inputs):

$$effective\_output[i] = base\_output[i] * (1 + prod\_mult)$$

**Example**:

- Base output: 1 green_circuit per craft
- Productivity module: +10% (```prod_mult``` = 0.1)
- Effective output: 1.1 green_circuits per craft

**Key Insight**: Productivity reduces crafts needed:

- To produce 1800 items/min with 1.1× productivity
- Requires only 1800/1.1 = 1636.36 crafts/min

### Handling Cycles, Byproducts, and Self-Contained Recipes

#### Cyclic Recipes

**Example**: catalyst_a ↔ catalyst_b cycle

- Recipe 1: `catalyst_a` + petroleum → `catalyst_b` + product
- Recipe 2: `catalyst_b` → `catalyst_a` + waste

The conservation equations naturally handle cycles by enforcing balance for cyclic intermediates:

```
For catalyst_a: production_a - consumption_a = 0
For catalyst_b: production_b - consumption_b = 0
```

The LP solver finds steady-state flow rates (e.g., both at 20 crafts/min) where catalysts circulate without accumulation, while the system produces the desired product.

**Key Insight**: Setting `b[i] = 0` for cyclic intermediates allows the solver to determine the optimal cycle flow rate automatically.

#### Byproducts

**Example**: Recipe produces both wanted item X and unwanted byproduct Y that is never consumed

**Implementation**: Byproducts use inequality constraints:

```python
if item in byproduct_items:
    prob += net_production >= 0  # Allow accumulation
```

This permits the recipe to run even though Y accumulates, as long as:

- The byproduct doesn't violate any constraints
- The recipe is needed to produce other items

# Design summary (concise)

## Factory — modeling choices

- Item balances / conservation (for each item i):

  $$\sum_{r} \mathrm{out}_{r,i}\,(1+\mathrm{prod}_{m_r})\,x_r - \sum_{r} \mathrm{in}_{r,i}\,x_r = b_i$$

  - Decision vars: $x_r$ = crafts/min for recipe $r$.
  - $b_{\text{target}}$ = target rate (equality), intermediate items: $b_i=0$, byproducts: $b_i\ge0$, raw items: $b_i\le0$ with supply caps.

- Raw consumption constraints:

  $$\text{net\_production}_i \le 0 \qquad\text{and}\qquad -\text{net\_production}_i \le \text{supply\_cap}_i$$

- Machine capacity (per machine type $m$):

  $$\sum_{r\in M} \frac{x_r}{\text{eff\_crafts\_per\_min}(r)} \le \text{max\_machines}_m$$

  with

  $$\text{eff\_crafts\_per\_min}(r)=\text{base\_speed}\,(1+\text{speed\_mult})\,\frac{60}{\text{time}_r}$$

- Module effects (per-machine-type): speed multiplies craft rate; productivity multiplies outputs only:

  $$\text{effective\_output}=\text{base\_output}\,(1+\text{prod\_mult})$$

- Cycles / byproducts / self-contained recipes: handled by conservation equations (set $b_i=0$ for cyclic intermediates). Byproducts allowed via inequality ($b_i\ge0$) so surplus accumulates but does not block feasible runs.

- Tie-breaking / determinism: primary objective is meet target; secondary minimize total machines (minimize $\sum_r x_r/\text{eff}_r$). Determinism via sorted iteration, fixed solver seed and single-threaded solve.

- Infeasibility detection & max-rate search: prefer LP infeasibility detection (CBC Simplex). If infeasible, binary search on target rate:

  - iterate: set mid=(low+high)/2; solve LP with target=mid; move low/high accordingly until desired precision.

## Belts — modeling choices

- Max-flow with lower bounds: transform to circulation problem:

  1. Set capacities: $c'_e = h_e - l_e$.
  2. Track node imbalances: for edge $u\to v$, subtract $l_e$ from $d_u$ and add $l_e$ to $d_v$.
  3. Solve feasibility (circulation) on modified capacities; reconstruct flow as $f_e = f'_e + l_e$.

- Node-splitting for node capacity $C_v$: replace $v$ with $v_{in}\to v_{out}$ and add edge $v_{in}\to v_{out}$ with capacity $C_v$; redirect incoming to $v_{in}$ and outgoing from $v_{out}$.

- Feasibility check strategy (two-phase):

  1. Phase 1 — circulation feasibility: add super-source/sink connecting according to imbalances and run max-flow; if demands unsatisfied → infeasible.
  2. Phase 2 — main flow: connect actual sources to virtual source and run max-flow to sink; check supply satisfied.

- Infeasibility certificates (min-cut): after max-flow, compute reachable set in residual graph; report

  - `cut_reachable` (S side),
  - `demand_balance` = total_supply − achieved_flow,
  - `tight_nodes` (nodes at capacity),
  - `tight_edges` (saturated edges crossing the cut).

## Numeric approach

- Tolerances: use tight epsilons to avoid floating errors, e.g. $\varepsilon=10^{-9}$ for conservation, capacity checks and cut saturation tests.

- Solver choices & rationale:

  - Factory: LP (PuLP + CBC) — natural, handles cycles/byproducts, reliable infeasibility detection and fast for intended sizes.
  - Belts: hand-implemented Edmonds–Karp (BFS) — deterministic, simple, no external deps; lower-bound transforms done prior to flow.

- Tie-breaking for determinism: sort keys (recipes, items, graph neighbors), fixed solver options, single-threaded execution; ensures identical outputs for same input.

## Failure modes & edge cases (brief)

- Cycles in recipes: set $b_i=0$ for intermediates; LP finds steady-state flows or sets rates to zero if unhelpful.

- Infeasible raw supplies or machine counts: LP returns infeasible; use binary search to find max feasible target and provide bottleneck hints (raw supply or machine caps).

- Degenerate or redundant recipes: LP objective (min machines) drives unused/inefficient recipes to zero; ties broken lexicographically.

- Disconnected belt components: max-flow yields zero flow for unreachable components; min-cut certificate identifies unreachable sources/edges.
