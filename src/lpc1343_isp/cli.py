"""Command line for the LPC1343 ISP harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lpc1343_isp.map import DEFAULT_FLOOR_BASE
from lpc1343_isp.machine import LpcMachine, RomImageError, RunResult


def format_result(result: RunResult, break_floor: bool) -> str:
    parts: list[str] = []
    if break_floor and result.floor is not None:
        shown = "19" if result.floor.refused else "0"
        parts.append(
            f"floor: dest={result.floor.dest:#010x} floor={result.floor.floor:#010x} "
            f"at={result.floor.at:#010x} -> {shown}"
        )
    body = result.text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if body:
        parts.append(body)
    return "\n".join(parts)


def _failure(machine: LpcMachine, result: RunResult) -> str:
    pages = " ".join(f"{page:#010x}" for page in machine.mmio_pages)
    trail = " ".join(f"{pc:#x}" for pc in list(machine.last_pcs)[-8:])
    extra = f" {result.detail}" if result.detail else ""
    return (
        f"stopped: {result.stop}{extra} pc={result.pc:#x} "
        f"steps={result.steps} mmio=[{pages}] trail=[{trail}]"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lpc-isp",
        description="Run the LPC1343 boot ROM ISP command loop. Addresses are decimal.",
    )
    parser.add_argument("-rom", required=True, type=Path, help="boot ROM image, base 0x1FFF0000")
    parser.add_argument("--crp", choices=("1", "2", "3", "none"), default="1")
    parser.add_argument(
        "--floor-base",
        default=hex(DEFAULT_FLOOR_BASE),
        help="word planted at flash 0x438; the ROM adds 0x200 (default 0x10000100)",
    )
    parser.add_argument(
        "--break",
        dest="break_at",
        choices=("floor",),
        default=None,
        help="print dest and floor when the write compare runs, then continue",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="send one ISP line and exit after the last --command (repeatable)",
    )
    parser.add_argument("--budget", type=int, default=2_000_000, help=argparse.SUPPRESS)
    return parser


def _machine_from(args: argparse.Namespace) -> LpcMachine | int:
    if not args.rom.is_file():
        print(f"ROM image not found: {args.rom}", file=sys.stderr)
        return 2
    try:
        floor_base = int(str(args.floor_base), 0)
    except ValueError:
        print(f"bad --floor-base {args.floor_base!r}", file=sys.stderr)
        return 2
    try:
        rom = args.rom.read_bytes()
    except OSError as exc:
        print(f"could not read {args.rom}: {exc}", file=sys.stderr)
        return 2
    try:
        return LpcMachine(rom, crp=args.crp, floor_base=floor_base, budget=args.budget)
    except (RomImageError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


def _run_line(machine: LpcMachine, line: str, break_floor: bool, interactive: bool) -> int:
    try:
        result = machine.command(line)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    rendered = format_result(result, break_floor)
    if rendered:
        print(rendered)
    if result.stop not in {"reply", "wait"}:
        print(_failure(machine, result), file=sys.stderr)
        return 1
    if interactive and result.stop == "wait" and not result.tx:
        print("(waiting for the next line)", file=sys.stderr)
    return 0


def _consume(
    machine: LpcMachine, lines: list[str], break_floor: bool, interactive: bool
) -> tuple[int, bool]:
    rc = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        stripped = line.strip()
        if stripped in {".quit", ".exit"}:
            return rc, break_floor
        if stripped == "":
            continue
        if stripped == ".reset":
            machine.reset()
            if interactive:
                print("reset")
            continue
        if stripped == ".break":
            break_floor = not break_floor
            if interactive:
                print("floor break on" if break_floor else "floor break off")
            continue
        status = _run_line(machine, line, break_floor, interactive)
        if status:
            rc = status
            if not interactive:
                return rc, break_floor
    return rc, break_floor


def _repl(machine: LpcMachine, break_floor: bool) -> int:
    rc = 0
    while True:
        try:
            line = input("isp> ")
        except EOFError:
            print()
            return rc
        except KeyboardInterrupt:
            print()
            return 130
        status, break_floor = _consume(machine, [line], break_floor, interactive=True)
        if line.strip() in {".quit", ".exit"}:
            return rc
        rc = max(rc, status)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    made = _machine_from(args)
    if isinstance(made, int):
        return made
    break_floor = args.break_at == "floor"
    if args.command:
        rc, _ = _consume(made, list(args.command), break_floor, interactive=False)
        return rc
    if sys.stdin.isatty():
        return _repl(made, break_floor)
    piped = [line.rstrip("\n") for line in sys.stdin]
    rc, _ = _consume(made, piped, break_floor, interactive=False)
    return rc
