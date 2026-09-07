# Disassembly

`disassemble(reader, address)` decodes one instruction without creating or
modifying a `Z80CPU`. The reader is called with wrapped 16-bit addresses and must
return byte integers. `disassemble_bytes(data, address)` decodes from a copied
sequence whose first byte is located at the supplied address.

Both functions return an immutable `Instruction` with:

- `address` and exact encoded `data`;
- uppercase `mnemonic` and structured `operands`;
- `size` and 16-bit `next_address`; and
- canonical human-readable `text`.

The decoder covers every base, CB, ED, DD, FD, DDCB, and FDCB form supported by
this instruction core, including undocumented index-byte and indexed copy forms,
and it treats a run of DD/FD prefixes (and DD/FD before ED) as one instruction
whose bytes include the stray prefixes, exactly as the core executes it.
Unsupported encodings raise `NotImplementedError`, matching the execution core's
deliberately bounded opcode surface.

## Side-effect-free reads

Disassembly is observation, so it must not alter the machine being observed. A
normal emulator memory read may acknowledge an interrupt, advance a FIFO, clear a
status bit, or otherwise touch a mapped device. For that reason the library does
not offer `cpu.disassemble()` and does not silently invoke `cpu.read_byte()`.

Hosts should expose an explicit side-effect-free peek operation:

```python
instruction = disassemble(machine.peek_byte, machine.pc)
print(f"{instruction.address:04X}: {instruction.text}")
```

If a host cannot safely peek a region, it should report that capability as
unsupported instead of routing debugging reads through device access methods.

## Formatting

Numeric operands use `0x` hexadecimal notation. Relative branches are resolved to
their absolute 16-bit destination. Indexed displacements retain their sign, for
example `(IX+0x05)` and `(IY-0x02)`. Indexed CB instructions expose their
undocumented destination register when the encoding copies the result.

Formatting is a presentation convenience. Debugger and agent integrations should
consume `mnemonic`, `operands`, and `data` rather than parsing `text`.
