"""Minimal bytearray-backed host for the public :mod:`z80_python` API."""

from z80_python import Z80CPU


class MinimalZ80Host(Z80CPU):
    """A CPU host with flat memory and deliberately inert I/O ports."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.ports = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return self.ports[addr & 0xFFFF]

    def write_port(self, addr: int, value: int) -> None:
        self.ports[addr & 0xFFFF] = value & 0xFF


def main() -> None:
    cpu = MinimalZ80Host()
    cpu.memory[:3] = bytes((0x3E, 0x2A, 0x3C))  # LD A,2Ah; INC A

    first_t_states = cpu.step()
    second_t_states = cpu.step()

    print(f"A=0x{cpu.a:02X}; T-states={first_t_states}+{second_t_states}")


if __name__ == "__main__":
    main()
