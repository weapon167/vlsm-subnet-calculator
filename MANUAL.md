# VLSM Subnet Calculator — User Manual

A complete reference for operating this tool: every command, every flag, worked examples, and what to expect in each situation. Keep this alongside the tool in your project folder.

---

## Quick Cheat Sheet

| I want to... | Command |
|---|---|
| Give departments/sites specific host counts and get subnets | `python vlsm_subnet_calculator.py vlsm <network> <hosts...> --labels <names...>` |
| Split a network into N equal pieces, maximizing hosts | `python vlsm_subnet_calculator.py subnets <network> <count>` |
| Find the smallest single route covering several subnets | `python vlsm_subnet_calculator.py summarize <subnet1> <subnet2> ...` |
| Run a calculation WITHOUT saving it or checking for conflicts | add `--no-save` to any `vlsm` or `subnets` command |
| Use a separate history file for a different project | add `--history <filename>.json` to any `vlsm` or `subnets` command |
| See what's already been allocated | open the `vlsm_history.json` file in a text editor |

---

## 1. Setup

Requires Python 3.9+, already built in — no installs needed. Run every command from inside the folder where `vlsm_subnet_calculator.py` lives:

```
cd "path\to\your\vlsm-subnet-calculator"
```

---

## 2. Command: `vlsm`

**What it's for:** you have a list of specific host-count requirements (departments, branch offices, VLANs — anything with a known number of devices) and you want each one sized to fit, largest first, with no wasted or overlapping addresses.

**Syntax:**
```
python vlsm_subnet_calculator.py vlsm <base_network> <host_count_1> <host_count_2> ... [--labels NAME1 NAME2 ...] [--history FILE] [--no-save]
```

**Example — the standard case:**
```
python vlsm_subnet_calculator.py vlsm 192.168.10.0/24 50 30 10 5 --labels Sales HR IT Finance
```
Produces a full table: subnet, mask, usable host range, usable count for each of the four, and saves all four to the history file.

**Rules to remember:**
- Host counts can be given in any order — the tool always sorts largest-first internally before allocating, then reports back in the order you typed them.
- `--labels`, if used, must have exactly one name per host count, in the same order.
- If there isn't enough room left in the network to fit every requirement, the whole command fails with a clear error — nothing partial gets saved.

---

## 3. Command: `subnets`

**What it's for:** you don't have specific host counts — you just need a fixed number of equal-sized subnets (e.g. "we're opening 12 identical branch sites"), and you want each one as large as possible.

**Syntax:**
```
python vlsm_subnet_calculator.py subnets <base_network> <count> [--labels NAME1 NAME2 ...] [--history FILE] [--no-save]
```

**Example:**
```
python vlsm_subnet_calculator.py subnets 172.20.0.0/16 12
```
Splits the network into the smallest number of equal blocks that gives you at least 12 pieces, using the fewest borrowed bits possible (so hosts per subnet are maximized).

**Rules to remember:**
- All resulting subnets are exactly the same size — there's no way to mix sizes in this command; use `vlsm` instead if sizes need to differ.
- If you give `--labels`, you need exactly one name per subnet requested.

---

## 4. Command: `summarize`

**What it's for:** the reverse direction — you already have several separate subnets (already allocated, already in use) and you want the single smallest address block that contains all of them, for a routing table summary route.

**Syntax:**
```
python vlsm_subnet_calculator.py summarize <subnet_1> <subnet_2> <subnet_3> ...
```

**Example:**
```
python vlsm_subnet_calculator.py summarize 10.30.0.0/24 10.30.1.0/24 10.30.2.0/24 10.30.3.0/24
```
Returns the smallest block covering all four — in this case `10.30.0.0/22`.

**Rules to remember:**
- Needs at least two subnets to summarize.
- The result may cover a few extra addresses beyond exactly what you listed — this is normal and expected, since a single block can only start and end on specific power-of-two boundaries. The tool tells you exactly how many extra addresses are included when this happens.
- This command does **not** check or write to the history file — it's a read-only calculation on subnets you give it directly.

---

## 5. History File & Conflict Checking

Every successful `vlsm` or `subnets` run writes its results into `vlsm_history.json` (created automatically the first time you run either command). Before handing out any new subnet, the tool checks it against everything already in that file.

**If there's an overlap, you'll see something like this, and nothing gets saved:**
```
CONFLICT: the following newly calculated subnet(s) overlap with subnets already recorded in the history file:
  - 10.20.0.0/23 (Sales), recorded 2026-09-30T08:02:13+00:00 from '10.20.0.0/16' via 'vlsm'

Nothing was saved. Choose a different base network or resolve the conflict before proceeding.
```
This is the tool protecting you from accidentally handing out an address range that's already assigned to something else, possibly from weeks or months earlier.

**Useful flags for managing this:**
- `--history myproject.json` — keep a separate history file per project, so different clients or sites don't check against each other's address space.
- `--no-save` — run a calculation purely as a "what if," without checking for conflicts and without recording the result. Good for testing ideas before committing to them.

**To review everything you've ever allocated:** just open `vlsm_history.json` in any text editor — it's a plain, readable list.

---

## 6. Errors You Might See, and What They Mean

| Error message contains... | What it means |
|---|---|
| "This tool supports IPv4 only" | You gave it an IPv6 network. This tool doesn't handle IPv6 — it's out of scope by design. |
| "Not enough address space left" | Your host or subnet requirements are bigger than the base network can hold. Use a larger network or reduce requirements. |
| "Got X labels but Y host requirements" | The number of names in `--labels` doesn't match the number of host counts or subnets given. |
| "CONFLICT: ... overlap with subnets already recorded" | The new allocation collides with something already saved in the history file. See Section 5. |
| "Provide at least two subnets to summarize" | `summarize` needs at least two subnets to compare — a single subnet has nothing to summarize against. |

---

## 7. Quick Reference — All Flags

| Flag | Works with | What it does |
|---|---|---|
| `--labels NAME1 NAME2 ...` | `vlsm`, `subnets` | Names each result instead of leaving it numbered |
| `--history FILE.json` | `vlsm`, `subnets` | Use a specific history file instead of the default |
| `--no-save` | `vlsm`, `subnets` | Skip conflict checking and don't record this run |

---

*Companion manual for `vlsm_subnet_calculator.py` — built by Nassif, CompTIA Network+ (N10-009) study project.*
