"""The smallest complete host: 64 KiB of RAM and nothing on the I/O bus.

The CPU takes its bus as callables. A bytearray's own ``__getitem__`` and
``__setitem__`` are enough because the core always passes a 16-bit address
and an 8-bit value; ``read_port``/``write_port`` default to an unconnected
bus (reads 0xFF, writes discarded).
"""

from z80_python import Z80CPU


def main() -> None:
    memory = bytearray(0x10000)
    cpu = Z80CPU(memory.__getitem__, memory.__setitem__)
    memory[:3] = bytes((0x3E, 0x2A, 0x3C))  # LD A,2Ah; INC A

    first_t_states = cpu.step()
    second_t_states = cpu.step()

    print(f"A=0x{cpu.a:02X}; T-states={first_t_states}+{second_t_states}")


if __name__ == "__main__":
    main()
