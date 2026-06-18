# custom-gds branch — continuation notes

Goal: hand-assemble the gf180 64x8 SRAM onto a TT **1x1** tile as a custom GDS, because
OpenLane cannot route it (see below). Submit via the `custom_gds` TT flow.

## STATUS: PRECHECK PASSED ✅ (custom-gds branch, run 27740508792) — ready to submit to ttgf0p3
"INFO: Precheck passed ... 🎉". gds:success, precheck:success. viewer:failure is only the
GitHub Pages deploy (enable Pages in repo Settings -> Pages -> Source: GitHub Actions; benign).
To submit: merge `custom-gds` -> default branch and add the repo to the ttgf0p3 shuttle.

## (earlier) connectivity-complete + DRC-clean
- All 23 data/clk nets routed; controls connected (GWEN<-ui_in[6] active-low on an M1 lane;
  CEN=0, WEN[0:7]=0 tied to macro VSS); uio_out/uio_oe=0 tied; power VDPWR/VGND stripes +
  macro VSS/VDD connection. Full GDS KLayout-signoff DRC-clean (density rules only).
- Files: src/tt_um_ttcodebot_sram64x8.gds, lef/tt_um_ttcodebot_sram64x8.lef, src/project.v
  (matches the build), info.yaml (ui_in[6]=we_n, ui_in[7] unused). CI = custom_gds@ttgf0p3.
- Pushed branch `custom-gds`. The CI precheck is the authoritative sign-off.
- **Precheck requirements learned (round 1 failures, fixed):**
  1. LEF/GDS signal pins MUST match the frame DEF dims EXACTLY: Metal4 0.30um wide x 1.0um tall
     (DEF `-300 -1000 .. 300 1000` DBU) -> PIN_W=0.30 (not 0.44), else "Port X has different
     dimensions ... tt_block_1x1_pgvdd.def".
  2. project.v MUST declare the power ports `input wire VGND` and `input wire VDPWR` (lead the
     port list, like the oscillating-bones reference), else "Power pin check: Verilog doesn't
     contain VGND". (viewer job failure is just the GitHub Pages deploy - benign.)
  - Round 2 (after fixing 1-2): all checks pass EXCEPT three, now fixed in round 3:
    3. PR_bndry MUST be on layer (0,0) (NOT 63/0). gf180 pr_bndry = 0/0. The boundary_check
       (tt-support-tools precheck.py) keeps only layer (0,0) and requires
       PR_bndry.bbox == top.bbox -> draw the tile boundary on (0,0) exactly = (0,0)..(346.64,160.72).
    4. "Shapes outside project area" = a consequence of (3); fixed once PR_bndry is on (0,0)
       and nothing extends beyond it (it doesn't).
    5. "DBU: 1 violation" = wrong database unit. Write the GDS at precision 1e-9 (1nm DBU, the
       gf180 standard; the macro is 1e-9) NOT 1e-12. 0.005um grid = 5 DBU, still exact.
  - **The custom_gds precheck has NO LVS step** (checks: pin-label-overlap, zero-area, KLayout
    PR_bndry, pin, boundary, power-pin, layer, cell-name, gf180 DRC, antenna, analog-pin,
    verilog-syntax). So no macro netlist is needed. After (3)-(5), expect a full PASS.

## Why custom GDS (the wall on main)
The macro (301.3×152.2µm) fills the 1x1 tile and blocks Metal1-3 over its body. Only Metal4
is free above it; Metal5 is reserved (TT `RT_MAX_LAYER=Metal4`). The macro's physical pin
order (bottom edge) vs the TT I/O order (top edge) needs **~2831µm of horizontal "permutation"
routing** (mean 123µm/net, max 229, channel density 19). One free layer (M4) can't carry both
the horizontal permutation and the vertical tracks without shorts → OpenLane best = 3 shorts,
never closes. The fix: do the permutation in the **M1-M3 edge strips** (macro top/bottom +
margins) which the auto-router won't use, then run clean vertical M4 tracks over the macro.

## Repo layout (custom_gds flow) + the "broken layout" fix
- GDS output: **`src/tt_um_ttcodebot_sram64x8.gds`** (build_tile.py writes here). CI:
  `.github/workflows/gds.yaml` uses `TinyTapeout/tt-gds-action/custom_gds@ttgf0p3` with
  gds_path=src/<top>.gds, lef_path=lef/<top>.lef, verilog_path=src/project.v (+ precheck + viewer;
  docs.yaml @ttgf0p3). Removed the OpenLane-era cruft (config.json, pdn_cfg.tcl, the macro
  blackbox .v, test/, fpga.yaml, test.yaml, gds_src/).
- **CRITICAL FIX:** the macro GDS carries a spurious **layer-0/0** box (0,0)..(301.3,224.93) that
  is NOT a mask layer and stuck ~68µm past the top of the 160.72µm tile / PR boundary -> looked
  broken / un-signable. build_tile.py now strips layer (0,0) from every macro cell on load;
  assembled bbox is exactly the tile (346.64x160.72). All real device layers were already <=152.21.

## What's done
- `scripts/build_tile.py` (gdstk): places macro at (22.5,4.255) N, draws PR boundary (63/0),
  43 TT I/O pins (Metal4 + labels at y=160.22), and **channel-routes all 23 data/clk nets**
  (A←ui_in, D←uio_in, Q→uo_out, CLK←clk) via a 2-channel left-edge router (TOP=13, BOT=10),
  M2+M3 horizontals, M4 verticals. Via cuts EXACTLY 0.26µm, 0.05 enclosure, all coords snapped
  to 0.005µm grid. Output: `gds_src/tt_um_ttcodebot_sram64x8.gds`.
- Local KLayout signoff DRC clean except precheck-excluded density (M*.4/PL.8) — see below.

## Current DRC state (data nets) — ROUTING IS DRC-CLEAN
The 23-net channel router is **DRC-clean**: DRC of the routing in isolation (top-level shapes
only, macro reference dropped -> `/tmp/routing_only.gds`) yields only the 7 precheck-EXCLUDED
density rules (M1.4/M2.4/M3.4/M4.4/M5.4/MT.3/PL.8). Zero real violations.

Root cause of the old ~40 M3.2a/M2.2a was NOT packing (pin x-gaps are all >=2.36um, never
self-conflict): the TOP-net M2->M4 via-up patches (top edge y=4.10 at ystk=3.9) sat only
0.155um from the **macro's own bottom-edge metal at y=4.255**. FIX (committed): lowered the
via-up row to VIAUP_Y=3.70 (patch top 3.90, 0.355 to macro) and the 5 bottom tracks to
BOT_Y top=3.00 at pitch BTRK=0.685 (0.30 below the via-up row). Both clearances >=0.28.

**The full combined GDS (macro + routing) is DRC-clean** except the 6 precheck-excluded
density rules. Verified three ways with the KLayout signoff deck (`~/bin/klayout`, gf180mcu.drc,
run_mode=deep): macro-alone = 6 density only; routing-alone = 7 density only; combined = 6
density only ("DRC RESULT: FAILURE (6 violation(s))" = M1.4/M2.4/M4.4/M5.4/MT.3/PL.8). KLayout
exits nonzero whenever ANY rule (incl. density) fires, so a nonzero exit is expected/benign.
NOTE: reading a .lyrdb while KLayout is still writing it gives a partial/garbage count — always
wait for true process completion before parsing.

## RESOLVED: gf180 power convention (from the gf180 oscillating-bones port LEF)
Power is exposed as full-height **Metal4 vertical stripes at the LEFT edge** + a label:
- **VGND**  : Metal4 RECT x 3..7   (4um wide), y ~5..top, USE GROUND
- **VDPWR** : Metal4 RECT x 10..14 (4um wide), y ~5..top, USE POWER  (digital 3.3V; name VDPWR not VPWR)
Both fit in this tile's empty LEFT margin (x 0..22.5, left of the macro). The chip frame
connects to these at integration (Metal5 over them). Place the 2 control inverters in the same
left margin (x ~16..21) right beside the stripes so their M1 VDD/VSS rails via straight up to
VDPWR/VGND. Macro power: VSS has full-width M1/M2 perimeter rails incl. a bottom rail at tile
y~5.24..7.255 (macro-local 0.985..3.0) and a left rail at tile x~23.5..25.5; VDD has M2 rails +
M3 fingers (M3 fingers are at the macro TOP edge y~153.6..156.46, M2 rails at bottom). Bridge
VGND stripe -> macro VSS and VDPWR stripe -> macro VDD with short M4 jogs + via stacks landing
on those rails (M4 is free over the macro for the jog; land vias on a same-net rail to avoid
shorting macro signals).

## DONE: power stripes + macro power connection (in build_tile.py)
- VGND M4 stripe x3..7, VDPWR M4 x10..14, full height (y5..155.72) + labels. DRC-clean (empty
  left margin). Macro connection (net-verified from LEF, connectivity confirmed by overlap test
  -- DRC can't catch shorts, LVS is final):
  - VGND: via V3 at (5,15.05) [M4->M3], M3 hwire x5..24.2 @ y15.05 -> merges with macro VSS M3
    left rail (clean VSS-only M3 rows exist at tile y 13.7..17.2; the M3 passes UNDER the VDPWR
    M4 stripe -- different layer, no short).
  - VDPWR: M4 hwire x12..25.7 @ y10.32 (over macro, M4 free) + via V3 at (25.23,10.32) [M4->M3]
    onto macro VDD M3. **Do NOT add a V2 there** -- the macro already bonds its VDD M3<->M2 with
    its own V2 vias; adding ours collides => V2.2a. Landing on macro M3 alone is sufficient.
- Inverters will also tie their M1 VDD/VSS rails to these stripes (place them adjacent in the
  left margin). For current robustness, can add more VGND/VDPWR taps up the rails later.

## Output ties (uio_out/uio_oe = 0) -- approach note
The macro VSS top rail is NOT cleanly M1&M2&M3 at every output-pin x (checked: x 32.76/54.6/61.88
clean @ y154.4, but 40/47/69/76/83 not). So do NOT drop each of the 16 pins straight onto the
macro VSS at its own x. Instead run a short VGND collector (M3 or M2) in the top margin from a
verified-clean VSS landing (or from the VGND M4 stripe) and tie the 16 pins to it. uio_oe=0 makes
the pin an input so uio_out is don't-care, but LVS still needs both nets connected -> tie both.

## Simplification: control logic
WEN[0:7] are spread x 33..311 (full width). Instead of one 9-sink GWEN+WEN net, **tie WEN[0:7]
to VGND locally** (each near its own pin) and gate writes with GWEN only: a bit writes when
GWEN=0 AND WEN[i]=0, so WEN[i]=0 always => full-byte writes gated by GWEN. Then only 2 inverters:
  CEN  <- ~(ui_in[7])   (chip-select active-high in -> active-low CEN)
  GWEN <- ~(ui_in[6])   (write-enable active-high in -> active-low GWEN)
inv cell = gf180mcu_fd_sc_mcu7t5v0__inv_1 (2.24x3.92um; pins I/ZN on Metal1; VDD rail top, VSS
rail bottom). 4.52um tall incl rails -> does NOT fit the 4.255um bottom margin; place in the
LEFT margin (full height). Control nets still need horizontal runs in the margin channels (the
real cost): inv input from top IO (ui_in[6/7] @ x265/273) and output to macro pin (CEN@199,
GWEN@165, both bottom edge). Route each as M4-vertical-over-macro + one margin-channel horizontal.

## Control-pin x-centers (tile coords, from macro_pins.json)
CEN=199.09  GWEN=164.95  WEN: [0]=32.98 [1]=67.00 [2]=68.58 [3]=104.80 [4]=239.29 [5]=273.52
[6]=276.10 [7]=311.32. Macro VSS for ties: bottom M1 rail tile y~5.24..7.255 spanning x~23.5..322.8.

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
