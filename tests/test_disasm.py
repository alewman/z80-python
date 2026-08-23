"""Structured disassembler contract and exhaustive supportedness tests."""

from collections.abc import Iterable

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import Instruction, disassemble, disassemble_bytes


@pytest.mark.parametrize(
    ("encoded", "address", "text", "next_address"),
    [
        (bytes((0x3E, 0x2A)), 0x1000, "LD A, 0x2A", 0x1002),
        (bytes((0x20, 0xFC)), 0x1000, "JR NZ, 0x0FFE", 0x1002),
        (bytes((0xCB, 0x7E)), 0x1000, "BIT 7, (HL)", 0x1002),
        (bytes((0xED, 0x4B, 0x34, 0x12)), 0x1000, "LD BC, (0x1234)", 0x1004),
        (bytes((0xDD, 0x36, 0xFE, 0x7F)), 0x1000, "LD (IX-0x02), 0x7F", 0x1004),
        (bytes((0xFD, 0xCB, 0x05, 0x00)), 0x1000, "RLC (IY+0x05), B", 0x1004),
        (bytes((0xDD, 0xCB, 0x80, 0xBE)), 0xFFFF, "RES 7, (IX-0x80)", 0x0003),
    ],
)
def test_representative_instruction_forms(
    encoded: bytes, address: int, text: str, next_address: int
) -> None:
    instruction = disassemble_bytes(encoded, address)

    assert instruction.text == text
    assert instruction.data == encoded
    assert instruction.size == len(encoded)
    assert instruction.next_address == next_address


def test_reader_wraps_across_end_of_address_space_without_mutating_a_cpu() -> None:
    memory = bytearray(0x10000)
    memory[0xFFFF], memory[0], memory[1] = 0xC3, 0x34, 0x12
    cpu = MinimalZ80Host()
    before = cpu.capture_state()

    instruction = disassemble(memory.__getitem__, 0xFFFF)

    assert instruction == Instruction(0xFFFF, bytes((0xC3, 0x34, 0x12)), "JP", ("0x1234",))
    assert cpu.capture_state() == before


@pytest.mark.parametrize("bad_value", [-1, 0x100, True, None])
def test_reader_rejects_non_byte_values(bad_value: object) -> None:
    with pytest.raises(ValueError, match="non-byte"):
        disassemble(lambda _address: bad_value, 0)


def test_byte_sequence_reports_truncation() -> None:
    with pytest.raises(ValueError, match="ended"):
        disassemble_bytes(bytes((0x21, 0x34)))


def _supported_by_cpu(encoded: Iterable[int]) -> bool:
    cpu = MinimalZ80Host()
    cpu.memory[0x1000 : 0x1008] = bytes(encoded)
    cpu.pc = 0x1000
    cpu.sp = 0x8000
    try:
        cpu.decode_and_execute()
    except NotImplementedError:
        return False
    return True


def _supported_by_disassembler(encoded: Iterable[int]) -> bool:
    try:
        disassemble_bytes(bytes(encoded), 0x1000)
    except NotImplementedError:
        return False
    return True


@pytest.mark.parametrize("opcode", range(256))
def test_base_supportedness_matches_execution_core(opcode: int) -> None:
    encoded = (opcode, 0, 0, 0, 0)
    assert _supported_by_disassembler(encoded) == _supported_by_cpu(encoded)


@pytest.mark.parametrize("prefix", (0xCB, 0xED))
@pytest.mark.parametrize("opcode", range(256))
def test_cb_and_ed_supportedness_matches_execution_core(prefix: int, opcode: int) -> None:
    encoded = (prefix, opcode, 0, 0, 0)
    assert _supported_by_disassembler(encoded) == _supported_by_cpu(encoded)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD))
@pytest.mark.parametrize("opcode", range(256))
def test_index_supportedness_matches_execution_core(prefix: int, opcode: int) -> None:
    encoded = (prefix, opcode, 0, 0, 0, 0)
    assert _supported_by_disassembler(encoded) == _supported_by_cpu(encoded)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD))
@pytest.mark.parametrize("opcode", range(256))
def test_index_cb_space_is_completely_decodable(prefix: int, opcode: int) -> None:
    instruction = disassemble_bytes(bytes((prefix, 0xCB, 0, opcode)))

    assert instruction.size == 4
