"""Z80 flag-register implementation and bit masks."""

FLAG_S = 0b1000_0000
FLAG_Z = 0b0100_0000
FLAG_Y = 0b0010_0000
FLAG_H = 0b0001_0000
FLAG_X = 0b0000_1000
FLAG_PV = 0b0000_0100
FLAG_N = 0b0000_0010
FLAG_C = 0b0000_0001


class Flags:
    """The Z80 F register, including the undocumented X/Y bits."""

    __slots__ = ("_byte",)

    def __init__(self, value: int = 0) -> None:
        self._byte = value & 0xFF

    def __int__(self) -> int:
        return self._byte

    def __repr__(self) -> str:
        return f"Flags(0x{self._byte:02X})"

    @property
    def byte(self) -> int:
        return self._byte

    @byte.setter
    def byte(self, value: int) -> None:
        self._byte = value & 0xFF

    @property
    def s(self) -> int:
        return (self._byte >> 7) & 1

    @s.setter
    def s(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_S) | ((value & 1) << 7)

    @property
    def z(self) -> int:
        return (self._byte >> 6) & 1

    @z.setter
    def z(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_Z) | ((value & 1) << 6)

    @property
    def y(self) -> int:
        return (self._byte >> 5) & 1

    @y.setter
    def y(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_Y) | ((value & 1) << 5)

    @property
    def h(self) -> int:
        return (self._byte >> 4) & 1

    @h.setter
    def h(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_H) | ((value & 1) << 4)

    @property
    def x(self) -> int:
        return (self._byte >> 3) & 1

    @x.setter
    def x(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_X) | ((value & 1) << 3)

    @property
    def pv(self) -> int:
        return (self._byte >> 2) & 1

    @pv.setter
    def pv(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_PV) | ((value & 1) << 2)

    @property
    def n(self) -> int:
        return (self._byte >> 1) & 1

    @n.setter
    def n(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_N) | ((value & 1) << 1)

    @property
    def c(self) -> int:
        return self._byte & 1

    @c.setter
    def c(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_C) | (value & 1)

    def set_xy(self, value: int) -> None:
        self._byte = (self._byte & ~(FLAG_X | FLAG_Y)) | (value & (FLAG_X | FLAG_Y))
