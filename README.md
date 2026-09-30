# VLSM Subnet Calculator

An IPv4 subnet planning tool with three commands, covering both directions of subnetting plus the routing-table optimization step that follows it:

- **`vlsm`** — allocate variable-sized subnets from a list of host counts (the standard VLSM problem)
- **`subnets`** — allocate N equal-sized subnets from a network, maximizing hosts per subnet (the reverse problem — "I need this many subnets")
- **`summarize`** — given several subnets, calculate the single smallest route that covers all of them (route summarization / supernetting, the mirror image of VLSM)

Every allocation from `vlsm` and `subnets` is checked against a local history file before being handed out, and refused — with the specific conflicting record shown — if it overlaps a subnet already recorded there. This is what makes the tool safe to use across multiple sessions rather than only within a single run.

This started as a practice project applying subnetting fundamentals from CompTIA Network+ (N10-009) study, and was expanded into a complete addressing-planning tool covering the real gaps a first version would hit in ongoing use at an actual organization.

## Requirements

- Python 3.9 or later (uses only the standard library — `ipaddress`, `argparse`, `json`, `pathlib`, `datetime` — no external dependencies)

## Commands

### `vlsm` — variable-sized allocation

```
python vlsm_subnet_calculator.py vlsm <base_network> <host_count_1> <host_count_2> ... [--labels NAME1 NAME2 ...]
```

Example:
```
python vlsm_subnet_calculator.py vlsm 10.20.0.0/16 300 120 60 25 200 --labels Sales Operations Finance IT Guest-WiFi
```

Requirements are sorted largest-first internally before allocation (the standard VLSM strategy — placing large subnets first prevents small ones from fragmenting the address space in a way that strands room needed by a later, larger one), then reported back in the order given.

### `subnets` — equal-sized allocation, maximize hosts

```
python vlsm_subnet_calculator.py subnets <base_network> <count> [--labels NAME1 NAME2 ...]
```

Example:
```
python vlsm_subnet_calculator.py subnets 172.16.0.0/16 30
```

This solves the reverse problem: given only a target number of subnets, it borrows the fewest possible bits (maximizing hosts per subnet) and returns that many equal-sized blocks. This is the calculation behind questions like "we need 30 branch office subnets from this /16, maximize hosts per site."

### `summarize` — route summarization

```
python vlsm_subnet_calculator.py summarize <subnet_1> <subnet_2> ...
```

Example:
```
python vlsm_subnet_calculator.py summarize 10.20.0.0/23 10.20.2.0/24 10.20.3.0/25 10.20.3.128/26 10.20.3.192/27
```

Given several previously allocated subnets, this calculates the smallest single CIDR block that covers all of them — the calculation used to collapse many specific routes into one summary route in a routing table, reducing table size and route-advertisement overhead. Because a single CIDR block can only start and end on power-of-two boundaries, the summary may cover a few addresses outside the original list — the tool reports exactly how many, so that's never a silent surprise.

## Persistence and conflict checking

Every successful `vlsm` or `subnets` run appends its allocated subnets to a local JSON history file (`vlsm_history.json` by default, in the current directory). Before any new allocation is finalized, the tool checks the newly calculated subnets against every subnet already in that file — as raw address ranges, independent of which base network they originally came from — and refuses the whole allocation if any overlap is found, printing exactly which prior subnet conflicts, when it was recorded, and which command produced it.

```
CONFLICT: the following newly calculated subnet(s) overlap with subnets already recorded in the history file:
  - 10.20.0.0/23 (Sales), recorded 2026-09-30T08:02:13+00:00 from '10.20.0.0/16' via 'vlsm'

Nothing was saved. Choose a different base network or resolve the conflict before proceeding.
```

This is what prevents the tool from confidently handing out an address range on a Thursday that was already assigned to a different department on Monday, simply because each run starts with no memory of previous ones by default.

Two flags control this behavior:
- `--history <path>` — use a different history file (useful for keeping separate projects' address plans from checking against each other)
- `--no-save` — skip the conflict check entirely and don't record this run (useful for scratch calculations that were never actually deployed)

## Real-World Example

**Scenario:** A network engineer receives the following request while setting up a new branch office:

> We've been allocated **10.20.0.0/16** for the new Nairobi branch. Departments and expected device counts are:
> - Sales & Marketing — 300 devices
> - Guest Wi-Fi — 200 devices
> - Operations — 120 devices
> - Finance — 60 devices
> - IT/Server room — 25 devices
>
> Send me the subnet for each department, and flag if we're allocating address space sensibly.

**Command:**
```
python vlsm_subnet_calculator.py vlsm 10.20.0.0/16 300 120 60 25 200 --labels Sales Operations Finance IT Guest-WiFi
```

**Output:**
```
Allocation Report for 10.20.0.0/16
==============================================================================================================
#  Label           Requested  Subnet (CIDR)       Mask             Usable Host Range                   Usable
--------------------------------------------------------------------------------------------------------------
1  Sales           300        10.20.0.0/23        255.255.254.0    10.20.0.1 - 10.20.1.254             510
2  Operations      120        10.20.3.0/25        255.255.255.128  10.20.3.1 - 10.20.3.126             126
3  Finance         60         10.20.3.128/26      255.255.255.192  10.20.3.129 - 10.20.3.190           62
4  IT              25         10.20.3.192/27      255.255.255.224  10.20.3.193 - 10.20.3.222           30
5  Guest-WiFi      200        10.20.2.0/24        255.255.255.0    10.20.2.1 - 10.20.2.254             254
--------------------------------------------------------------------------------------------------------------
Address space used:  992 / 65536 (1.5%)
Address space free:  64544
```

**Interpretation:** each department gets the smallest subnet that comfortably fits its headcount. The 1.5% utilization is expected rather than wasteful here — a /16 is typically allocated with significant headroom for future growth (new departments, additional branch sites, or device count increases), not sized tightly to current needs alone. Six months later, if Legal is approved for 15 hosts, running `vlsm 10.20.0.0/16 15 --labels Legal` will now correctly detect and refuse any overlap with the five subnets above, since they're already in the history file from this run.

## How It Works

**`vlsm`:** for each host count, find the smallest number of host bits `n` such that `2^n − 2` covers the requirement, giving a prefix of `32 − n`. Sort largest-first, then walk a running address "cursor" through the base network: before placing each subnet, advance the cursor to the next valid boundary for that subnet's block size if it isn't already aligned, place the subnet, and move the cursor past it. Report results back in the original input order.

**`subnets`:** find the smallest number of bits `n` such that `2^n ≥` the requested subnet count, add that to the base network's prefix length, then take the first N subnets of that resulting size — this is the "maximize hosts" strategy, since borrowing the fewest bits leaves the most bits for hosts.

**`summarize`:** find the lowest address and highest address across all given subnets, then search downward from `/32` for the largest prefix (smallest block) that, once aligned to a valid boundary, still covers the entire range.

**Conflict checking:** every subnet is compared to history file entries as a pure integer range (`network_address` to `broadcast_address`), so overlaps are caught even between allocations made from completely different base networks or in completely separate sessions.

## Strengths

- Correct across octet boundaries in every position — the tool works with the full 32-bit address as a single integer via Python's `ipaddress` library rather than octet-by-octet, so it never makes the "wrong bucket" mistake that's easy to make by hand when a subnet crosses from one octet into the next.
- Covers both directions of the subnetting problem (host-count-driven and subnet-count-driven) plus the summarization step that follows deployment, rather than only the first calculation.
- Persistent and safe across sessions — allocations made weeks apart are checked against each other, not just within a single run.
- Fails safely and specifically: invalid networks, mismatched label counts, running out of address space, and history conflicts all produce a clear, specific error rather than a silent wrong answer.

## Limitations

- **IPv4 only, by design rather than by oversight.** The prefix and block-size math throughout is written for a 32-bit address space; IPv6 networks are rejected with a clear error on every command rather than silently miscalculated. This is a genuine scope decision, not an unfinished corner: internal enterprise LAN addressing — the work this tool targets — remains predominantly IPv4, with adoption inside company networks estimated around 30% even as public internet traffic approaches 50% IPv6 (Internet Society Pulse data). A dual-stack version would need a parallel set of functions built on 128-bit math, since IPv6's addressing model (no broadcast address, host counts effectively unlimited per subnet) makes the underlying logic different enough that it isn't a small patch on top of this one.
- **The `subnets` command always takes the first N contiguous blocks from the start of the base network.** It doesn't attempt to place them around existing history file entries — if the very first block it would choose already conflicts, the whole run is refused rather than the tool searching for the next available position further into the address space. Working around a conflict currently means manually choosing a different (typically smaller) base network and re-running.
- **History file conflict checking assumes single-user, single-machine use.** It's a local JSON file with no locking — running two allocations against the same history file at the exact same moment could both read the file before either has written, and neither would see the other's new subnet. Fine for one engineer's own planning; not a substitute for a real multi-user IPAM system in a team setting.
- **`summarize` finds the smallest covering block, not necessarily the most efficient real-world route set.** In practice, a router might advertise two or three summary routes instead of one slightly-too-large one, if that avoids wasting a large amount of unused address space in the routing table. This tool always returns a single block; choosing between one loose summary versus several tighter ones is a judgment call left to the engineer.

## Author

Built by Nassif — part of a CompTIA Network+ (N10-009) study project applying subnetting and VLSM fundamentals to a working tool.
