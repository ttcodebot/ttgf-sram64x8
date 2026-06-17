<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This project brings the Open Circuit Design **gf180 64x8 SRAM** macro
(`gf180mcu_ocd_ip_sram__sram64x8m8wm1`, 64 words × 8 bits = 512 bits) out onto a single
Tiny Tapeout 1x1 digital tile. The macro is a hard block (301.3 × 152.2 µm) that nearly
fills the tile; the only added logic is a thin wrapper that maps the macro's synchronous,
active-low control interface onto the Tiny Tapeout pins.

The memory is **synchronous**: every operation happens on the rising edge of `clk`.
A single byte is read or written per cycle.

Pin map:

| Tiny Tapeout pin | Function |
|------------------|----------|
| `ui[5:0]`        | address `A[5:0]` (selects one of 64 words) |
| `ui[6]`          | `we` — 1 = write the byte on `uio[7:0]`, 0 = read |
| `ui[7]`          | `cs` — chip select, 1 = enabled, 0 = standby/deselected |
| `uio[7:0]`       | `D[7:0]` write data (the bidirectional pins are used as **inputs**) |
| `uo[7:0]`        | `Q[7:0]` read data |
| `clk`            | SRAM clock |

The wrapper inverts the control signals because the macro's `CEN` (chip enable),
`GWEN` (global write enable) and `WEN` (per-bit write enable) are all **active-low**.
`rst_n` and `ena` are unused — the SRAM has no reset.

**Important:** the macro becomes operational only after it has been *deselected then
selected* once (a `cs` 0 → 1 transition, i.e. `CEN` high → low). Drive `cs = 0` for a
cycle or two after power-up before the first real access.

## How to test

All operations are clocked; hold each set of inputs stable across a rising edge of `clk`.
Because this is a hard memory macro, use a clock period of at least ~60 ns (≈16 MHz or
slower) for reliable behavioral/silicon operation.

1. **Activate:** set `cs = 0` (deselected) for one or two clock cycles, then set `cs = 1`.
2. **Write:** set `ui[5:0]` to the address, `ui[6] = 1` (we), `ui[7] = 1` (cs), put the
   byte on `uio[7:0]`, and pulse the clock. The byte is stored at that address.
3. **Read:** set `ui[5:0]` to the address, `ui[6] = 0` (read), `ui[7] = 1` (cs), and pulse
   the clock. The stored byte appears on `uo[7:0]`.

The cocotb testbench in `test/` writes distinct values across a spread of addresses
(including the corners 0 and 63), reads them all back, then overwrites one address and
confirms the others are undisturbed.

## External hardware

None. Drive the address/data/control pins from the Tiny Tapeout demo board (or another
design on the same tile) and observe the read data on the output pins.
