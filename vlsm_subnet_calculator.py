#!/usr/bin/env python3
"""
VLSM Subnet Calculator
-----------------------
Given a base network and a list of required host counts, this tool
allocates Variable Length Subnet Mask (VLSM) subnets automatically,
sorted largest-first (the standard allocation strategy), and prints
a full addressing table: subnet, mask, prefix, network address,
broadcast address, usable host range, and usable host count.

Author:Lord Nassif — CompTIA Network+ / VLSM practice project.

Usage examples:
    python3 vlsm_subnet_calculator.py 192.168.10.0/24 50 30 10 5
    python3 vlsm_subnet_calculator.py 172.16.0.0/16 500 200 100 50 20
"""

import argparse
import ipaddress
import sys


def hosts_to_prefix(host_count: int) -> int:
    """Return the smallest /prefix (largest number) that fits host_count
    usable hosts, using the 2^n - 2 rule."""
    if host_count <= 0:
        raise ValueError("Host count must be a positive integer.")
    n = 1
    while (2 ** n) - 2 < host_count:
        n += 1
    return 32 - n


def allocate_vlsm(base_network: str, host_requirements: list[int]):
    """Allocate VLSM subnets for each host requirement from base_network.

    Requirements are sorted largest-first before allocation, which is the
    standard approach: it prevents small subnets from fragmenting the
    address space in a way that strands room for a later, larger one.
    """
    network = ipaddress.ip_network(base_network, strict=True)
    # Keep track of original order so we can report back in the order
    # the user asked, even though we allocate largest-first internally.
    indexed = sorted(
        enumerate(host_requirements), key=lambda pair: pair[1], reverse=True
    )

    allocations = []
    cursor = int(network.network_address)
    network_end = int(network.broadcast_address)

    for original_index, hosts_needed in indexed:
        prefix = hosts_to_prefix(hosts_needed)
        block_size = 2 ** (32 - prefix)

        # Align cursor up to the next valid boundary for this block size.
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
                "subnet": subnet,
            }
        )
        cursor += block_size

    # Return in the original input order for a readable report.
    allocations.sort(key=lambda a: a["original_index"])
    return allocations


def print_report(base_network: str, allocations: list[dict]) -> None:
    total_available = ipaddress.ip_network(base_network).num_addresses
    used = sum(a["subnet"].num_addresses for a in allocations)

    print(f"\nVLSM Allocation Report for {base_network}")
    print("=" * 78)
    header = (
        f"{'#':<3}{'Requested':<11}{'Subnet (CIDR)':<20}{'Mask':<17}"
        f"{'Usable Host Range':<36}{'Usable':<7}"
    )
    print(header)
    print("-" * 94)

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
        print(
            f"{idx:<3}{a['hosts_requested']:<11}{str(subnet):<20}"
            f"{str(subnet.netmask):<17}{host_range:<36}{usable:<7}"
        )

    print("-" * 94)
    print(f"Address space used:  {used} / {total_available} "
          f"({used/total_available:.1%})")
    print(f"Address space free:  {total_available - used}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Allocate VLSM subnets for a list of host requirements."
    )
    parser.add_argument(
        "network",
        help="Base network in CIDR form, e.g. 192.168.10.0/24",
    )
    parser.add_argument(
        "hosts",
        nargs="+",
        type=int,
        help="One or more required host counts, e.g. 50 30 10 5",
    )
    args = parser.parse_args()

    try:
        allocations = allocate_vlsm(args.network, args.hosts)
        print_report(args.network, allocations)
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
