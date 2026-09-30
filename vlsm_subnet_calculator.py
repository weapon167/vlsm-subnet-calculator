#!/usr/bin/env python3
"""
VLSM Subnet Calculator
-----------------------
An IPv4 subnet planning tool with three commands:

  vlsm       Allocate variable-sized subnets from a list of host counts
             (the standard VLSM problem: "each department needs this many
             hosts, give me the addressing plan").

  subnets    Allocate N equal-sized subnets from a network, maximizing
             hosts per subnet (the reverse problem: "I need this many
             subnets, don't care about exact host count, use the fewest
             bits possible").

  summarize  Given several subnets, calculate the single smallest route
             that covers all of them (route summarization / supernetting
             — the mirror image of VLSM, used to keep routing tables small).

Every allocation from `vlsm` and `subnets` is checked against a local
history file before being handed out, and refused if it overlaps a
subnet already recorded there. This prevents the tool from silently
handing out addresses that were already assigned in an earlier run.

Author: built with Claude for Lord Nassif — CompTIA Network+ / VLSM practice project.

Usage examples:
    python3 vlsm_subnet_calculator.py vlsm 192.168.10.0/24 50 30 10 5 --labels Sales HR IT Finance
    python3 vlsm_subnet_calculator.py subnets 172.16.0.0/16 30
    python3 vlsm_subnet_calculator.py summarize 10.20.0.0/23 10.20.2.0/24 10.20.3.0/25
"""

import argparse
import ipaddress
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HISTORY_FILE = "vlsm_history.json"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def require_ipv4(network: ipaddress._BaseNetwork, context: str = "This tool") -> None:
    """Raise a clear error if network is IPv6. Every command's prefix and
    block-size math assumes a 32-bit address space."""
    if isinstance(network, ipaddress.IPv6Network):
        raise ValueError(
            f"{context} supports IPv4 only. The prefix and block-size math "
            "assumes a 32-bit address space and will not produce correct "
            "results for IPv6 (/128) networks."
        )


def hosts_to_prefix(host_count: int) -> int:
    """Return the smallest /prefix (largest number) that fits host_count
    usable hosts, using the 2^n - 2 rule."""
    if host_count <= 0:
        raise ValueError("Host count must be a positive integer.")
    n = 1
    while (2 ** n) - 2 < host_count:
        n += 1
    return 32 - n


def subnets_to_bits(subnet_count: int) -> int:
    """Return the smallest number of bits n such that 2^n >= subnet_count."""
    if subnet_count <= 0:
        raise ValueError("Subnet count must be a positive integer.")
    n = 0
    while (2 ** n) < subnet_count:
        n += 1
    return n


# ---------------------------------------------------------------------------
# History file: persistence + conflict checking
# ---------------------------------------------------------------------------

def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Could not read history file {path}: {exc}")


def save_history(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def find_conflicts(new_subnets: list[ipaddress.IPv4Network], history: list[dict]) -> list[dict]:
    """Return history records whose address range overlaps any subnet in
    new_subnets. Overlap is checked as raw integer ranges, independent of
    which base network each allocation originally came from."""
    conflicts = []
    for record in history:
        hist_net = ipaddress.ip_network(record["subnet"], strict=True)
        hist_start = int(hist_net.network_address)
        hist_end = int(hist_net.broadcast_address)
        for new_net in new_subnets:
            new_start = int(new_net.network_address)
            new_end = int(new_net.broadcast_address)
            if not (new_end < hist_start or new_start > hist_end):
                conflicts.append(record)
                break
    return conflicts


def append_to_history(path: Path, base_network: str, command: str,
                       allocations: list[dict]) -> None:
    history = load_history(path)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for a in allocations:
        history.append(
            {
                "subnet": str(a["subnet"]),
                "label": a.get("label"),
                "base_network": base_network,
                "command": command,
                "recorded_at": timestamp,
            }
        )
    save_history(path, history)


# ---------------------------------------------------------------------------
# Command: vlsm (variable-sized allocation from host counts)
# ---------------------------------------------------------------------------

def allocate_vlsm(base_network: str, host_requirements: list[int],
                   labels: list[str] | None = None) -> list[dict]:
    network = ipaddress.ip_network(base_network, strict=True)
    require_ipv4(network, "The vlsm command")

    if labels is not None and len(labels) != len(host_requirements):
        raise ValueError(
            f"Got {len(labels)} labels but {len(host_requirements)} host "
            "requirements — these lists must be the same length."
        )

    indexed = sorted(
        enumerate(host_requirements), key=lambda pair: pair[1], reverse=True
    )

    allocations = []
    cursor = int(network.network_address)
    network_end = int(network.broadcast_address)

    for original_index, hosts_needed in indexed:
        prefix = hosts_to_prefix(hosts_needed)
        block_size = 2 ** (32 - prefix)

        if cursor % block_size != 0:
            cursor += block_size - (cursor % block_size)

        if cursor + block_size - 1 > network_end:
            raise ValueError(
                f"Not enough address space left in {base_network} to fit "
                f"a subnet for {hosts_needed} hosts (needs /{prefix})."
            )

        subnet = ipaddress.ip_network((cursor, prefix), strict=True)
        allocations.append(
            {
                "original_index": original_index,
                "hosts_requested": hosts_needed,
                "label": labels[original_index] if labels else None,
                "subnet": subnet,
            }
        )
        cursor += block_size

    allocations.sort(key=lambda a: a["original_index"])
    return allocations


# ---------------------------------------------------------------------------
# Command: subnets (equal-sized allocation, maximize hosts, reverse problem)
# ---------------------------------------------------------------------------

def allocate_equal_subnets(base_network: str, subnet_count: int,
                            labels: list[str] | None = None) -> tuple[list[dict], int]:
    """Split base_network into exactly `subnet_count` equal-sized subnets,
    using the fewest borrowed bits possible (maximizing hosts per subnet).
    Returns (allocations, new_prefix)."""
    network = ipaddress.ip_network(base_network, strict=True)
    require_ipv4(network, "The subnets command")

    if labels is not None and len(labels) != subnet_count:
        raise ValueError(
            f"Got {len(labels)} labels but {subnet_count} subnets requested — "
            "these must match."
        )

    bits_needed = subnets_to_bits(subnet_count)
    new_prefix = network.prefixlen + bits_needed

    if new_prefix > 32:
        raise ValueError(
            f"{base_network} does not have enough address space to create "
            f"{subnet_count} subnets."
        )

    all_subnets = list(network.subnets(new_prefix=new_prefix))
    chosen = all_subnets[:subnet_count]

    allocations = []
    for i, subnet in enumerate(chosen):
        allocations.append(
            {
                "original_index": i,
                "hosts_requested": None,
                "label": labels[i] if labels else None,
                "subnet": subnet,
            }
        )
    return allocations, new_prefix


# ---------------------------------------------------------------------------
# Command: summarize (route summarization / supernetting)
# ---------------------------------------------------------------------------

def summarize_routes(cidrs: list[str]) -> ipaddress.IPv4Network:
    """Return the smallest single CIDR block that fully covers every
    given subnet. This is the reverse of VLSM: instead of splitting a
    block into smaller pieces, it finds the smallest block that several
    existing pieces fit inside — used to keep routing tables small by
    advertising one summary route instead of many specific ones."""
    if len(cidrs) < 2:
        raise ValueError("Provide at least two subnets to summarize.")

    networks = [ipaddress.ip_network(c, strict=True) for c in cidrs]
    for n in networks:
        require_ipv4(n, "The summarize command")

    start = min(int(n.network_address) for n in networks)
    end = max(int(n.broadcast_address) for n in networks)

    for prefix in range(32, -1, -1):
        block_size = 2 ** (32 - prefix)
        aligned_start = start - (start % block_size)
        aligned_end = aligned_start + block_size - 1
        if aligned_end >= end:
            return ipaddress.ip_network((aligned_start, prefix), strict=True)

    # Unreachable in practice: prefix 0 always covers the full address space.
    raise ValueError("Could not compute a summary route.")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_allocation_report(base_network: str, allocations: list[dict],
                             show_requested: bool = True) -> None:
    total_available = ipaddress.ip_network(base_network).num_addresses
    used = sum(a["subnet"].num_addresses for a in allocations)
    has_labels = any(a.get("label") for a in allocations)

    col_widths = {"idx": 3, "label": 16, "req": 11, "subnet": 20, "mask": 17,
                  "range": 36, "usable": 7}
    total_width = sum(col_widths.values()) if (has_labels and show_requested) else 94

    print(f"\nAllocation Report for {base_network}")
    print("=" * total_width)

    header = f"{'#':<3}"
    if has_labels:
        header += f"{'Label':<16}"
    if show_requested:
        header += f"{'Requested':<11}"
    header += f"{'Subnet (CIDR)':<20}{'Mask':<17}{'Usable Host Range':<36}{'Usable':<7}"
    print(header)
    print("-" * total_width)

    for a in allocations:
        subnet = a["subnet"]
        hosts = list(subnet.hosts())
        if hosts:
            host_range = f"{hosts[0]} - {hosts[-1]}"
            usable = len(hosts)
        else:
            host_range = "(none - /31 or /32)"
            usable = 0

        idx = a["original_index"] + 1
        row = f"{idx:<3}"
        if has_labels:
            row += f"{(a.get('label') or '-'):<16}"
        if show_requested:
            req = a["hosts_requested"] if a["hosts_requested"] is not None else "-"
            row += f"{req:<11}"
        row += f"{str(subnet):<20}{str(subnet.netmask):<17}{host_range:<36}{usable:<7}"
        print(row)

    print("-" * total_width)
    print(f"Address space used:  {used} / {total_available} "
          f"({used/total_available:.1%})")
    print(f"Address space free:  {total_available - used}\n")


def handle_conflicts_or_save(base_network: str, command: str,
                              allocations: list[dict], history_path: Path,
                              no_save: bool) -> None:
    if no_save:
        return
    history = load_history(history_path)
    conflicts = find_conflicts([a["subnet"] for a in allocations], history)
    if conflicts:
        print("\nCONFLICT: the following newly calculated subnet(s) overlap "
              "with subnets already recorded in the history file:",
              file=sys.stderr)
        for c in conflicts:
            label = f" ({c['label']})" if c.get("label") else ""
            print(f"  - {c['subnet']}{label}, recorded {c['recorded_at']} "
                  f"from '{c['base_network']}' via '{c['command']}'",
                  file=sys.stderr)
        print("\nNothing was saved. Choose a different base network or "
              "resolve the conflict before proceeding.", file=sys.stderr)
        sys.exit(2)

    append_to_history(history_path, base_network, command, allocations)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--history", default=DEFAULT_HISTORY_FILE,
        help=f"Path to the history file used for conflict checking "
             f"(default: {DEFAULT_HISTORY_FILE} in the current directory).",
    )
    common.add_argument(
        "--no-save", action="store_true",
        help="Skip conflict checking and do not record this allocation "
             "in the history file.",
    )

    parser = argparse.ArgumentParser(
        description="IPv4 subnet planning: VLSM allocation, equal-split "
                     "allocation, and route summarization.",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="mode", required=True)

    vlsm_parser = subparsers.add_parser(
        "vlsm", help="Allocate variable-sized subnets from host counts.",
        parents=[common],
    )
    vlsm_parser.add_argument("network", help="Base network, e.g. 192.168.10.0/24")
    vlsm_parser.add_argument("hosts", nargs="+", type=int,
                              help="Required host counts, e.g. 50 30 10 5")
    vlsm_parser.add_argument("--labels", nargs="+", default=None,
                              help="Optional names, same order as hosts.")

    subnets_parser = subparsers.add_parser(
        "subnets", help="Allocate N equal-sized subnets, maximizing hosts.",
        parents=[common],
    )
    subnets_parser.add_argument("network", help="Base network, e.g. 172.16.0.0/16")
    subnets_parser.add_argument("count", type=int, help="Number of subnets needed.")
    subnets_parser.add_argument("--labels", nargs="+", default=None,
                                 help="Optional names, one per subnet.")

    summarize_parser = subparsers.add_parser(
        "summarize", help="Find the smallest route that covers several subnets."
    )
    summarize_parser.add_argument("subnets", nargs="+",
                                   help="Two or more subnets in CIDR form.")

    args = parser.parse_args()
    history_path = Path(args.history)

    try:
        if args.mode == "vlsm":
            allocations = allocate_vlsm(args.network, args.hosts, args.labels)
            print_allocation_report(args.network, allocations, show_requested=True)
            handle_conflicts_or_save(args.network, "vlsm", allocations,
                                      history_path, args.no_save)

        elif args.mode == "subnets":
            allocations, new_prefix = allocate_equal_subnets(
                args.network, args.count, args.labels
            )
            print(f"\n{args.count} subnets requested from {args.network} "
                  f"-> each sized /{new_prefix}")
            print_allocation_report(args.network, allocations, show_requested=False)
            handle_conflicts_or_save(args.network, "subnets", allocations,
                                      history_path, args.no_save)

        elif args.mode == "summarize":
            summary = summarize_routes(args.subnets)
            print(f"\nSummary route for {len(args.subnets)} subnets:")
            for c in args.subnets:
                print(f"  - {c}")
            print(f"\n  => {summary}  (mask {summary.netmask})")
            covered = summary.num_addresses
            requested = sum(ipaddress.ip_network(c, strict=True).num_addresses
                             for c in args.subnets)
            if covered > requested:
                print(f"\nNote: this summary also covers "
                      f"{covered - requested} address(es) not in your "
                      f"original list — that's expected; a single CIDR "
                      f"block can only align on power-of-two boundaries.\n")

    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
