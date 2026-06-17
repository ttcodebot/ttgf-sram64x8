# SPDX-FileCopyrightText: 2026 ttcodebot
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

# The behavioral SRAM model specifies a minimum cycle time of 55.6 ns and
# invalidates reads on any clock/width violation, so drive it well under that.
CLK_NS = 100


def encode_ui(addr, we, cs):
    """Pack the wrapper's input pins: ui[5:0]=addr, ui[6]=we, ui[7]=cs."""
    return (addr & 0x3F) | ((we & 1) << 6) | ((cs & 1) << 7)


async def sram_write(dut, addr, data):
    # Set up inputs in the low phase so setup/hold around the rising edge is met.
    await FallingEdge(dut.clk)
    dut.ui_in.value = encode_ui(addr, we=1, cs=1)
    dut.uio_in.value = data & 0xFF
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")


async def sram_read(dut, addr):
    await FallingEdge(dut.clk)
    dut.ui_in.value = encode_ui(addr, we=0, cs=1)
    dut.uio_in.value = 0
    await RisingEdge(dut.clk)
    # Let the registered read output (qo_reg) settle after the edge.
    await Timer(CLK_NS // 4, units="ns")
    return int(dut.uo_out.value)


@cocotb.test()
async def test_sram_read_write(dut):
    dut._log.info("Start gf180 64x8 SRAM test")
    cocotb.start_soon(Clock(dut.clk, CLK_NS, units="ns").start())

    # Reset / TT housekeeping. The SRAM has no reset; ena/rst_n are ignored by
    # the wrapper, but we still drive the standard TT sequence.
    dut.ena.value = 1
    dut.rst_n.value = 0
    dut.uio_in.value = 0
    # Hold the macro DESELECTED (cs=0 -> CEN high) initially.
    dut.ui_in.value = encode_ui(0, we=0, cs=0)
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    # First select (cs 0->1 => CEN 1->0) makes the memory operational.
    await FallingEdge(dut.clk)
    dut.ui_in.value = encode_ui(0, we=0, cs=1)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Walk a spread of addresses (corners + a few interior) with distinct data.
    patterns = {0: 0xA5, 1: 0x5A, 7: 0xFF, 8: 0x00, 31: 0x3C, 42: 0x42, 63: 0xC3}

    for addr, data in patterns.items():
        await sram_write(dut, addr, data)

    for addr, data in patterns.items():
        got = await sram_read(dut, addr)
        assert got == data, f"addr {addr}: wrote {data:#04x}, read {got:#04x}"

    dut._log.info("Read-back matched for all addresses")

    # Overwrite an address and confirm the new value sticks (and others don't move).
    await sram_write(dut, 42, 0x99)
    got = await sram_read(dut, 42)
    assert got == 0x99, f"overwrite addr 42: read {got:#04x}"
    got = await sram_read(dut, 7)
    assert got == 0xFF, f"addr 7 disturbed after overwrite: read {got:#04x}"

    dut._log.info("All SRAM checks passed")
