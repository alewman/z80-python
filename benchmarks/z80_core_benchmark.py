"""Reproducible microbenchmarks for the pure-Python Z80 instruction core."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from z80_python import Z80CPU


class BenchmarkCPU(Z80CPU):
    """Flat-memory benchmark host with deterministic bytearray-backed I/O."""

    def __init__(self, program: bytes) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.ports = bytearray(0x10000)
        self.memory[: len(program)] = program
        for offset in range(0x100):
            self.memory[0x5000 + offset] = (offset * 17 + 3) & 0xFF
            self.ports[0x2000 + offset] = (offset * 29 + 5) & 0xFF

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return self.ports[addr & 0xFFFF]

    def write_port(self, addr: int, value: int) -> None:
        self.ports[addr & 0xFFFF] = value & 0xFF


@dataclass(frozen=True)
class Workload:
    """Named deterministic program executed through :meth:`Z80CPU.step`."""

    name: str
    description: str
    program: bytes


@dataclass(frozen=True)
class Sample:
    """One timed benchmark sample."""

    elapsed_seconds: float
    t_states: int


@dataclass(frozen=True)
class BenchmarkResult:
    """All samples and derived rates for one workload."""

    name: str
    description: str
    instruction_count: int
    samples: tuple[Sample, ...]
    median_seconds: float
    instructions_per_second: float
    t_states_per_second: float


WORKLOADS: Final[tuple[Workload, ...]] = (
    Workload(
        "base",
        "base opcode fetch/decode, loads, ALU, and branch",
        bytes(
            (
                0x3E,
                0x31,  # LD A,31h
                0x06,
                0x17,  # LD B,17h
                0x80,  # ADD A,B
                0xA8,  # XOR B
                0x0C,  # INC C
                0x15,  # DEC D
                0x5F,  # LD E,A
                0xC3,
                0x00,
                0x00,  # JP 0000h
            )
        ),
    ),
    Workload(
        "indexed_cb",
        "DD/FD, DDCB/FDCB, CB dispatch, and indexed memory",
        bytes(
            (
                0xDD,
                0x21,
                0x00,
                0x40,  # LD IX,4000h
                0xFD,
                0x21,
                0x00,
                0x41,  # LD IY,4100h
                0xDD,
                0x36,
                0x01,
                0x81,  # LD (IX+1),81h
                0xDD,
                0xCB,
                0x01,
                0x06,  # RLC (IX+1)
                0xFD,
                0x36,
                0xFF,
                0x55,  # LD (IY-1),55h
                0xFD,
                0xCB,
                0xFF,
                0x8E,  # RES 1,(IY-1)
                0xCB,
                0x00,  # RLC B
                0xC3,
                0x00,
                0x00,  # JP 0000h
            )
        ),
    ),
    Workload(
        "block_io",
        "ED block output/input with deterministic host I/O",
        bytes(
            (
                0x01,
                0x10,
                0x20,  # LD BC,2010h
                0x21,
                0x00,
                0x50,  # LD HL,5000h
                0xED,
                0xA3,  # OUTI
                0x01,
                0x10,
                0x21,  # LD BC,2110h
                0xED,
                0xA2,  # INI
                0xC3,
                0x00,
                0x00,  # JP 0000h
            )
        ),
    ),
)


def _execute(cpu: BenchmarkCPU, instruction_count: int) -> int:
    step = cpu.step
    t_states = 0
    for _ in range(instruction_count):
        t_states += step()
    return t_states


def run_benchmark(
    workload: Workload,
    *,
    instruction_count: int,
    repeats: int,
    warmup_instructions: int,
) -> BenchmarkResult:
    """Run one workload with all host/program setup outside timed loops."""
    if instruction_count < 1 or repeats < 1 or warmup_instructions < 0:
        raise ValueError("instruction_count/repeats must be positive and warmup non-negative")

    if warmup_instructions:
        _execute(BenchmarkCPU(workload.program), warmup_instructions)

    samples: list[Sample] = []
    for _ in range(repeats):
        cpu = BenchmarkCPU(workload.program)
        started = time.perf_counter()
        t_states = _execute(cpu, instruction_count)
        elapsed = time.perf_counter() - started
        samples.append(Sample(elapsed, t_states))

    median_seconds = statistics.median(sample.elapsed_seconds for sample in samples)
    median_t_states = statistics.median(sample.t_states for sample in samples)
    return BenchmarkResult(
        name=workload.name,
        description=workload.description,
        instruction_count=instruction_count,
        samples=tuple(samples),
        median_seconds=median_seconds,
        instructions_per_second=instruction_count / median_seconds,
        t_states_per_second=median_t_states / median_seconds,
    )


def _metadata() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }


def _print_results(results: list[BenchmarkResult]) -> None:
    metadata = _metadata()
    print(
        f"Python: {metadata['python_implementation']} {metadata['python_version']}\n"
        f"Platform: {metadata['platform']}"
    )
    for result in results:
        sample_text = ", ".join(f"{sample.elapsed_seconds:.6f}" for sample in result.samples)
        print(f"\n{result.name}: {result.description}")
        print(f"  instructions: {result.instruction_count:,} per sample")
        print(f"  samples (s): [{sample_text}]")
        print(f"  median (s): {result.median_seconds:.6f}")
        print(f"  instructions/s: {result.instructions_per_second:,.0f}")
        print(f"  T-states/s: {result.t_states_per_second:,.0f}")


def _write_json(path: Path, results: list[BenchmarkResult]) -> None:
    payload = {
        **_metadata(),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=int, default=500_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup-instructions", type=int, default=25_000)
    parser.add_argument(
        "--workload",
        choices=("all", *(workload.name for workload in WORKLOADS)),
        default="all",
    )
    parser.add_argument("--json", type=Path, help="also write machine-readable results")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    selected = [
        workload
        for workload in WORKLOADS
        if args.workload == "all" or workload.name == args.workload
    ]
    try:
        results = [
            run_benchmark(
                workload,
                instruction_count=args.instructions,
                repeats=args.repeats,
                warmup_instructions=args.warmup_instructions,
            )
            for workload in selected
        ]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_results(results)
    if args.json is not None:
        _write_json(args.json, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
