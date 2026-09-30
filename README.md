# VLSM Subnet Calculator

A command-line tool that automates Variable Length Subnet Mask (VLSM) design. Give it a base network and a list of required host counts, and it works out the smallest subnet that fits each requirement, places every subnet back-to-back with no overlaps and no wasted alignment gaps where avoidable, and prints a full addressing table.

This is the exact calculation a network engineer does by hand when a business hands over a set of department or site host-count requirements and expects an IP addressing plan back — automated so it can be run in seconds and re-run instantly if requirements change.

## Features

- Automatic prefix calculation from a host count, using the standard `2ⁿ − 2` usable-host rule
- Largest-first allocation, the standard VLSM strategy that prevents small subnets from fragmenting address space and stranding room needed by a later, larger subnet
- Full addressing table output: subnet in CIDR notation, subnet mask, usable host range, and usable host count per subnet
- Address space utilization summary (used vs. free), so you can immediately tell whether an allocation is efficient or whether a larger block should have been requested
- Input validation with clear error messages if a network is malformed or there isn't enough address space to fit every requirement

## Requirements

- Python 3.9 or later (uses the built-in `ipaddress` module — no external dependencies)

## Usage

```
python vlsm_subnet_calculator.py <base_network> <host_count_1> <host_count_2> ...
```

- `base_network` — the network you've been allocated, in CIDR form (e.g. `192.168.10.0/24`)
- `host_count_*` — one or more required host counts, in any order

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
python vlsm_subnet_calculator.py 10.20.0.0/16 300 120 60 25 200
```

**Output:**

```
VLSM Allocation Report for 10.20.0.0/16
==============================================================================
#  Requested  Subnet (CIDR)       Mask             Usable Host Range                   Usable
----------------------------------------------------------------------------------------------
1  300        10.20.0.0/23        255.255.254.0    10.20.0.1 - 10.20.1.254             510
2  120        10.20.3.0/25        255.255.255.128  10.20.3.1 - 10.20.3.126             126
3  60         10.20.3.128/26      255.255.255.192  10.20.3.129 - 10.20.3.190           62
4  25         10.20.3.192/27      255.255.255.224  10.20.3.193 - 10.20.3.222           30
5  200        10.20.2.0/24        255.255.255.0    10.20.2.1 - 10.20.2.254             254
----------------------------------------------------------------------------------------------
Address space used:  992 / 65536 (1.5%)
Address space free:  64544
```

**Interpretation:** each department gets the smallest subnet that comfortably fits its headcount, with no manual subnetting required. The 1.5% utilization is expected rather than wasteful here — a /16 is typically allocated with significant headroom for future growth (new departments, additional branch sites, or device count increases), not sized tightly to current needs alone.

## How It Works

1. **Requirement sizing** — for each host count, the tool finds the smallest number of host bits `n` such that `2ⁿ − 2` is greater than or equal to the requirement, then derives the subnet prefix as `32 − n`.
2. **Largest-first ordering** — requirements are processed from largest to smallest before allocation, regardless of the order they were entered.
3. **Sequential placement** — a running address "cursor" tracks the next free address. Before placing each subnet, the cursor is advanced to the next valid boundary for that subnet's block size if it isn't already aligned, then the subnet is placed and the cursor moves past it.
4. **Reporting** — results are re-sorted back into the original input order and printed as a table, alongside a summary of total address space used and remaining.

## Author

Built by Nassif — part of a CompTIA Network+ (N10-009) study project applying subnetting and VLSM fundamentals to a working tool.
