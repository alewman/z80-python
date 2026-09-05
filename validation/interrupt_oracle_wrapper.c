// Thin, struct-free C API around superzazu/z80 (an independent, separately
// zexdoc/zexall-certified Z80 core) so it can be driven from Python via
// plain ctypes function calls, without replicating its bitfield struct
// layout. Used only by validation/interrupt_crosscheck.py as a second
// implementation to cross-check interrupt-lifecycle sequencing against; it
// is not part of the shipped z80_python package.
#include "z80.h"
#include <string.h>

static z80 g;
static uint8_t mem[65536];

static uint8_t rd(void* ud, uint16_t addr) { (void)ud; return mem[addr]; }
static void wr(void* ud, uint16_t addr, uint8_t val) { (void)ud; mem[addr] = val; }
static uint8_t pin(z80* z, uint8_t port) { (void)z; (void)port; return 0xFF; }
static void pout(z80* z, uint8_t port, uint8_t val) { (void)z; (void)port; (void)val; }

void w_reset(void) {
  memset(mem, 0, sizeof(mem));
  z80_init(&g);
  g.read_byte = rd;
  g.write_byte = wr;
  g.port_in = pin;
  g.port_out = pout;
}

void w_set_mem(int addr, int val) { mem[addr & 0xFFFF] = (uint8_t)val; }
int w_get_mem(int addr) { return mem[addr & 0xFFFF]; }

void w_set_pc(int v) { g.pc = (uint16_t)v; }
int w_get_pc(void) { return g.pc; }
void w_set_sp(int v) { g.sp = (uint16_t)v; }
int w_get_sp(void) { return g.sp; }
void w_set_i(int v) { g.i = (uint8_t)v; }
int w_get_i(void) { return g.i; }
void w_set_r(int v) { g.r = (uint8_t)v; }
int w_get_r(void) { return g.r; }
void w_set_a(int v) { g.a = (uint8_t)v; }
int w_get_a(void) { return g.a; }
void w_set_iff1(int v) { g.iff1 = v ? 1 : 0; }
int w_get_iff1(void) { return g.iff1; }
void w_set_iff2(int v) { g.iff2 = v ? 1 : 0; }
int w_get_iff2(void) { return g.iff2; }
void w_set_im(int v) { g.interrupt_mode = (uint8_t)v; }
int w_get_im(void) { return g.interrupt_mode; }
void w_set_halted(int v) { g.halted = v ? 1 : 0; }
int w_get_halted(void) { return g.halted; }
void w_set_iff_delay(int v) { g.iff_delay = (uint8_t)v; }
int w_get_iff_delay(void) { return g.iff_delay; }

unsigned long w_get_cyc(void) { return g.cyc; }

void w_step(void) { z80_step(&g); }
void w_gen_nmi(void) { z80_gen_nmi(&g); }
void w_gen_int(int data) { z80_gen_int(&g, (uint8_t)data); }
