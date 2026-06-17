/*
 * Copyright (c) 2026 ttcodebot
 * SPDX-License-Identifier: Apache-2.0
 *
 * 64x8 SRAM (gf180mcu_ocd_ip_sram__sram64x8m8wm1, by Open Circuit Design) brought out on a
 * Tiny Tapeout 1x1 digital tile. The 301.3 x 152.2 um macro nearly fills the 346.64 x 160.72 um
 * tile, so the only logic added is the thin wrapper below.
 *
 * Pin map (1 word = 8 bits, 64 words = 6-bit address):
 *   ui_in[5:0] = address A[5:0]
 *   ui_in[6]   = we   (write this cycle: 1 = write D, 0 = read)
 *   ui_in[7]   = cs   (chip select: 1 = enabled, 0 = standby/low-power)
 *   uio_in[7:0]= D[7:0] write data   (uio used as inputs)
 *   uo_out[7:0]= Q[7:0] read data
 *   clk        = SRAM clock          (ena / rst_n unused — SRAM has no reset)
 */

`default_nettype none

module tt_um_ttcodebot_sram64x8 (
    input  wire [7:0] ui_in,    // address[5:0], we, cs
    output wire [7:0] uo_out,   // read data Q[7:0]
    input  wire [7:0] uio_in,   // write data D[7:0]
    output wire [7:0] uio_out,  // unused (driven 0)
    output wire [7:0] uio_oe,   // all inputs
    input  wire       ena,      // unused
    input  wire       clk,      // SRAM clock
    input  wire       rst_n     // unused (SRAM has no reset)
);

  // The bidirectional pins are used purely as inputs (write data).
  assign uio_out = 8'b0;
  assign uio_oe  = 8'b0;

  wire [5:0] addr = ui_in[5:0];
  wire       we   = ui_in[6];
  wire       cs   = ui_in[7];

  // CEN / GWEN / WEN are all ACTIVE-LOW on this macro. librelane connects the macro's
  // VDD/VSS power pins via PDN_MACRO_CONNECTIONS, so no power ports are wired here.
  gf180mcu_ocd_ip_sram__sram64x8m8wm1 sram (
      .CLK  (clk),
      .CEN  (~cs),          // chip enable (low = enabled)
      .GWEN (~we),          // global write enable (low = write)
      .WEN  ({8{~we}}),     // per-bit write enable (low = write that bit) — write all 8 when we
      .A    (addr),
      .D    (uio_in),       // write data
      .Q    (uo_out)        // read data
  );

  // Silence unused-signal lint (SRAM has no reset / enable).
  wire _unused = &{ena, rst_n, 1'b0};

endmodule

`default_nettype wire
