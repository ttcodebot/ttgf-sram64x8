# custom-gds branch — continuation notes

Goal: hand-assemble the gf180 64x8 SRAM onto a TT **1x1** tile as a custom GDS, because
OpenLane cannot route it (see below). Submit via the `custom_gds` TT flow.

## Why custom GDS (the wall on main)
The macro (301.3×152.2µm) fills the 1x1 tile and blocks Metal1-3 over its body. Only Metal4
is free above it; Metal5 is reserved (TT `RT_MAX_LAYER=Metal4`). The macro's physical pin
order (bottom edge) vs the TT I/O order (top edge) needs **~2831µm of horizontal "permutation"
routing** (mean 123µm/net, max 229, channel density 19). One free layer (M4) can't carry both
the horizontal permutation and the vertical tracks without shorts → OpenLane best = 3 shorts,
never closes. The fix: do the permutation in the **M1-M3 edge strips** (macro top/bottom +
margins) which the auto-router won't use, then run clean vertical M4 tracks over the macro.

## What's done
- `scripts/build_tile.py` (gdstk): places macro at (22.5,4.255) N, draws PR boundary (63/0),
  43 TT I/O pins (Metal4 + labels at y=160.22), and **channel-routes all 23 data/clk nets**
  (A←ui_in, D←uio_in, Q→uo_out, CLK←clk) via a 2-channel left-edge router (TOP=13, BOT=10),
  M2+M3 horizontals, M4 verticals. Via cuts EXACTLY 0.26µm, 0.05 enclosure, all coords snapped
  to 0.005µm grid. Output: `gds_src/tt_um_ttcodebot_sram64x8.gds`.
- Local KLayout signoff DRC clean except precheck-excluded density (M*.4/PL.8) — see below.

## TODO (to finish)
1. **Fix 1 M4-vertical collision**: D[3].ix (236.60) vs D[4].px (236.95), 0.35µm. Nudge the
   TOP-net px vertical with a short M3 jog, or force that net to the BOT channel. (Connectivity
   bug — DRC won't catch it; LVS will.)
2. **Control nets**: instantiate 2 inverters `gf180mcu_fd_sc_mcu7t5v0__inv_1` in a side margin:
   CEN←~(ui_in[7]=cs), and GWEN+WEN[7:0]←~(ui_in[6]=we) (one inverter drives GWEN + all 8 WEN).
   Place cell GDS instances + route inv in/out + power pins.
3. **Ties**: uio_out[7:0]=0 and uio_oe[7:0]=0 → tie to a `__tielo`/`__filltie` cell output (1-2
   cells driving all 16 I/O pins), or connect those I/O pins to VGND.
4. **Power**: connect macro VDD/VSS (Metal3 fingers top+bottom, internally bussed) + the stdcell
   power pins to the frame VPWR/VGND (Metal4 pins along the top edge). Add VPWR/VGND M4 pins +
   labels matching the frame (see tt_block_1x1_pgvdd.def positions).
5. **LVS**: magic extract the assembled GDS → netgen vs a structural gate netlist (wrapper +
   macro behavioral blackbox + inv + tielo). `~/bin/magic`, `~/bin/netgen`.
6. **LEF**: magic `lef write` (pins on Metal4; SIZE = tile). Put in `lef/`.
7. **info.yaml + CI**: switch to the custom_gds flow — copy oscillating-bones `.github/workflows`
   (`tt-gds-action/custom_gds@ttgf0p3` + precheck + viewer + docs). NOTE: current sram repo
   workflows use `@ttgf26a`; the custom_gds flow ref is `@ttgf0p3`. Provide `gds/` + `lef/`.
8. Push branch, run CI precheck.

## Key data (already extracted)
- `scripts/macro_pins.json`: all macro pin rects. Signal pins = Metal2, macro-local y 0-3
  (bottom edge), tile x = macro_x + 22.5.
- TT 1x1 I/O x-positions: in `build_tile.py` `IOX`.
- gf180 layers: M1=34/0 M2=36/0 M3=42/0 M4=46/0 (pins /10), V1=35 V2=38 V3=40, PR_bndry=63/0.
- Rules: M1 w0.23/s0.23, M2/M3 w0.28/s0.28, M4 w0.23/s0.28; via cut **exactly 0.26**, enc 0.05.
- Precheck-EXCLUDED DRC (don't chase): density M1.4/M2.4/M4.4/M5.4/MT.3 + PL.8 (poly density);
  filled at chip integration.
- Authoritative DRC locally: `~/bin/klayout -b -r <pdk>/libs.tech/klayout/tech/drc/gf180mcu.drc
  -rd input=... -rd topcell=tt_um_ttcodebot_sram64x8 -rd variant=gf180mcuD -rd run_mode=deep
  -rd report=out.lyrdb -rd decks=all,-antenna`
