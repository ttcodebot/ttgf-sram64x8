#!/usr/bin/env python3
"""
Hand-assemble the gf180 64x8 SRAM onto a Tiny Tapeout 1x1 tile as a custom GDS.

Why custom (not OpenLane): the macro fills the tile and blocks Metal1-3 over its
body, leaving only Metal4 free above it. The macro pin order (bottom edge) vs the
TT I/O order (top edge) needs ~2831um of horizontal "permutation" routing, which a
single free layer (M4) cannot carry together with the vertical tracks without shorts.
Here we do that permutation deliberately in the M1-M3 *edge strips* (top & bottom),
which the auto-router won't exploit, then run clean vertical M4 tracks over the macro.

Output: gds_src/tt_um_ttcodebot_sram64x8.gds
"""
import gdstk, json, os

um = 1.0
DBU = 0.005

# --- gf180 GDS layers (layer/datatype) ---
L = {
    'M1':(34,0),'M2':(36,0),'M3':(42,0),'M4':(46,0),
    'V1':(35,0),'V2':(38,0),'V3':(40,0),
    'M1pin':(34,10),'M2pin':(36,10),'M3pin':(42,10),'M4pin':(46,10),
    'M1lab':(34,10),'M4lab':(46,10),
    'PRbnd':(0,0),   # PR boundary placeholder (set below)
}
PRBND = (63,0)   # gf180 PR_bndry

# --- design rules (um) ---
RUL = {
    'M1':dict(w=0.23,s=0.23),'M2':dict(w=0.28,s=0.28),
    'M3':dict(w=0.28,s=0.28),'M4':dict(w=0.23,s=0.28),
}
VIA = {  # gf180 via cuts are EXACTLY 0.26um; enclosure 0.07 -> 0.40 patch (>= M3 min-area 0.1444)
    'V1':dict(cut=0.26,enc=0.07,below='M1',above='M2'),
    'V2':dict(cut=0.26,enc=0.07,below='M2',above='M3'),
    'V3':dict(cut=0.26,enc=0.07,below='M3',above='M4'),
}
GRID = 0.005
def g(v):  # snap to manufacturing grid
    return round(round(v/GRID)*GRID, 3)
WIRE = 0.40          # signal wire width (= via patch, no notch; M3 min-area ok)
TRK  = 0.70          # horizontal track pitch (0.40 wire + 0.30 space > 0.28)

# --- tile / macro geometry (um) ---
TILE_W, TILE_H = 346.64, 160.72
MACRO = 'gf180mcu_ocd_ip_sram__sram64x8m8wm1'
MACRO_W, MACRO_H = 301.3, 152.21
MX, MY = 22.5, 4.255          # macro lower-left in tile (orientation N)
IO_Y = 160.22                 # I/O pin row (top edge)

# macro signal pin x-centers (tile coords) from the LEF
pins = json.load(open(os.path.join(os.path.dirname(__file__),'macro_pins.json')))
def pin_xc(name):
    r=[x for x in pins[name]['rects'] if x[0]=='Metal2' and x[2]<5][0]
    return (r[1]+r[3])/2 + MX

# TT 1x1 I/O pin x-positions (tile coords), all Metal4 at IO_Y
IOX = {
 'clk':331.24,'ena':338.52,'rst_n':323.96,
 **{f'ui_in[{i}]':x for i,x in enumerate([316.68,309.40,302.12,294.84,287.56,280.28,273.00,265.72])},
 **{f'uio_in[{i}]':x for i,x in enumerate([258.44,251.16,243.88,236.60,229.32,222.04,214.76,207.48])},
 **{f'uo_out[{i}]':x for i,x in enumerate([200.20,192.92,185.64,178.36,171.08,163.80,156.52,149.24])},
 **{f'uio_out[{i}]':x for i,x in enumerate([141.96,134.68,127.40,120.12,112.84,105.56,98.28,91.00])},
 **{f'uio_oe[{i}]':x for i,x in enumerate([83.72,76.44,69.16,61.88,54.60,47.32,40.04,32.76])},
}

lib = gdstk.Library(name='ttsram', unit=1e-6, precision=1e-12)
top = lib.new_cell('tt_um_ttcodebot_sram64x8')

# place macro
macrolib = gdstk.read_gds('macro/%s/%s.gds'%(MACRO,MACRO))
# The macro GDS carries a spurious layer-0/0 boundary box (0,0)..(301.3,224.93) that is NOT a
# real mask layer and sticks ~68um ABOVE the 160.72um tile, poking out of the PR boundary.
# Strip all layer-0/0 shapes from every macro cell so the placed macro fits within the tile.
for c in macrolib.cells:
    c.filter([(0,0)], remove=True)
macrocell = [c for c in macrolib.cells if c.name==MACRO][0]
for c in macrolib.cells:
    lib.add(c)
top.add(gdstk.Reference(macrocell, (MX, MY)))

# ---------- helpers ----------
def rect(layer, x1,y1,x2,y2):
    x1,y1,x2,y2 = g(x1),g(y1),g(x2),g(y2)
    if x2<x1: x1,x2=x2,x1
    if y2<y1: y1,y2=y2,y1
    top.add(gdstk.rectangle((x1,y1),(x2,y2), layer=L[layer][0], datatype=L[layer][1]))

def hwire(layer, x1, x2, yc, w=WIRE):
    rect(layer, x1, yc-w/2, x2, yc+w/2)
def vwire(layer, xc, y1, y2, w=WIRE):
    rect(layer, xc-w/2, y1, xc+w/2, y2)

def via(kind, xc, yc):
    xc,yc = g(xc),g(yc)
    v=VIA[kind]; c=v['cut']; e=v['enc']
    half=c/2
    top.add(gdstk.rectangle((g(xc-half),g(yc-half)),(g(xc+half),g(yc+half)), layer=L[kind][0], datatype=L[kind][1]))
    p=c/2+e
    for m in (v['below'],v['above']):
        rect(m, xc-p, yc-p, xc+p, yc+p)

def via_stack(layers, xc, yc):
    """layers e.g. ['M2','M3','M4'] -> place V2,V3 vias to connect them."""
    order={'M1':1,'M2':2,'M3':3,'M4':4}
    for a,b in zip(layers, layers[1:]):
        k={('M1','M2'):'V1',('M2','M3'):'V2',('M3','M4'):'V3'}[(a,b)]
        via(k, xc, yc)

# ---------- PR boundary ----------
top.add(gdstk.rectangle((0,0),(TILE_W,TILE_H), layer=PRBND[0], datatype=PRBND[1]))

# ---------- I/O pins (Metal4 shapes + labels at top edge) ----------
PIN_W=0.44; PIN_H=1.0
def io_pin(name):
    x=IOX[name]
    rect('M4', x-PIN_W/2, IO_Y-PIN_H/2, x+PIN_W/2, IO_Y+PIN_H/2)
    top.add(gdstk.Label(name,(x,IO_Y), layer=L['M4pin'][0], texttype=L['M4pin'][1]))
for nm in IOX: io_pin(nm)

# ---------- power pins (Metal4 left-edge stripes, gf180 TT convention) ----------
# From the gf180 oscillating-bones port LEF: VGND = M4 x3..7, VDPWR = M4 x10..14, full height.
# Both sit in this tile's empty LEFT margin (x<22.5). The chip frame connects to them via M5.
PWR_Y0, PWR_Y1 = 5.0, TILE_H-5.0
def pwr_stripe(name, x0, x1):
    rect('M4', x0, PWR_Y0, x1, PWR_Y1)
    top.add(gdstk.Label(name,((x0+x1)/2,(PWR_Y0+PWR_Y1)/2), layer=L['M4pin'][0], texttype=L['M4pin'][1]))
pwr_stripe('VGND',  3.0,  7.0)
pwr_stripe('VDPWR', 10.0, 14.0)

# ---------- connect stripes to macro power rails (left edge) ----------
# Macro exposes a VSS rail (M1/M2/M3 stacked) at tile x~24.06 and a VDD rail (M2/M3) at x~25.23,
# running up the left edge. Landings net-verified from the LEF (clean VSS-only M3 rows at the
# macro edge at tile y 13.7..17.2; VDD M2 INT M3 at x25.23, y 8.6..12). Connectivity is verified
# by landing net (DRC cannot catch shorts -> LVS is the final check).
# VGND: stripe(M4) -> M3 (passes UNDER the VDPWR M4 stripe) -> merge with macro VSS M3 left rail.
def connect_vgnd(yc):
    via('V3', 5.0, yc)                 # VGND M4 stripe -> M3
    hwire('M3', 5.0, 24.2, yc)         # M3 across margin, merges with macro VSS M3 (x22.7..24.3)
# VDPWR: stripe(M4) extended OVER the macro (M4 free there; passes over VSS rail harmlessly) and
# vias down only at the VDD rail x25.23 (clear of the VSS rail which ends at x24.62).
def connect_vdpwr(yc):
    hwire('M4', 12.0, 25.7, yc)        # extend VDPWR M4 to the VDD rail
    via('V3', 25.23, yc)               # M4->M3 onto macro VDD M3 (macro bonds VDD M3<->M2 itself;
                                       # adding our own V2 here collides with the macro's V2 -> V2.2a)
connect_vgnd(15.05)
connect_vdpwr(10.32)

# ---------- channel router for the permutation ----------
# Net list: (macro_pin, io_name). Data + clk are direct; control via inverters (added later).
data_nets = []
for i in range(6):  data_nets.append((f'A[{i}]',  f'ui_in[{i}]'))
for i in range(8):  data_nets.append((f'D[{i}]',  f'uio_in[{i}]'))
for i in range(8):  data_nets.append((f'Q[{i}]',  f'uo_out[{i}]'))
data_nets.append(('CLK','clk'))

# horizontal channel track y-positions (in the free margins). Two layers (M2,M3) per channel.
# Bottom margin is only 4.255um tall and must hold 5 horizontal rows PLUS the TOP-net via-up
# row (which lifts those nets onto M4 to cross the macro). The via-up makes M2+M3 patches that
# must clear (a) the macro's own bottom-edge metal at y=4.255 by >=0.28 and (b) the topmost
# bottom-channel track by >=0.28. Solving both: 5 rows at pitch 0.685 topping out at y=3.00,
# and the via-up row centered at VIAUP_Y=3.70 (patch 3.50..3.90: 0.35 to macro, 0.30 to top row).
BTRK = 0.685
BOT_Y = [round(0.26 + k*BTRK, 3) for k in range(5)]         # 0.26..3.00  (top row clears via-up row)
TOP_Y = [round(157.0 + k*TRK, 3) for k in range(5)]         # 157.0..159.8 (above macro top 156.465, below IO 160.22)
VIAUP_Y = 3.70           # TOP-net M2->M4 via-up row (bottom margin); clears macro (4.255) + top track
MACRO_BOT = MY            # 4.255  (macro signal pins at y 4.255..7.255)
MACRO_PIN_TOP = MY+3.0    # 7.255

nets = []
for mp, io in data_nets:
    px, ix = pin_xc(mp), IOX[io]
    nets.append(dict(mp=mp, io=io, px=px, ix=ix, lo=min(px,ix), hi=max(px,ix)))

# balance assignment to TOP/BOTTOM by greedy lowest-density
import math
def density_at(assigned, x):
    return sum(1 for n in assigned if n['lo']-0.001<=x<=n['hi']+0.001)
nets.sort(key=lambda n:-(n['hi']-n['lo']))
chan={'TOP':[], 'BOT':[]}
for n in nets:
    mid=(n['lo']+n['hi'])/2
    dt=max(density_at(chan['TOP'],x) for x in (n['lo'],mid,n['hi']))
    db=max(density_at(chan['BOT'],x) for x in (n['lo'],mid,n['hi']))
    c='TOP' if dt<=db else 'BOT'
    chan[c].append(n); n['chan']=c

# left-edge track assignment within each channel (per 2 layers M2/M3 interleaved by track index)
def assign_tracks(members, ntracks):
    members=sorted(members,key=lambda n:n['lo'])
    track_end=[-1e9]*ntracks
    for n in members:
        placed=False
        for t in range(ntracks):
            if n['lo'] > track_end[t]+0.34:
                n['trk']=t; track_end[t]=n['hi']; placed=True; break
        if not placed:
            raise SystemExit(f"channel overflow ({n['chan']}): need more than {ntracks} tracks")
    return members

NT_BOT=len(BOT_Y)*2  # M2+M3
NT_TOP=len(TOP_Y)*2
assign_tracks(chan['BOT'], NT_BOT)
assign_tracks(chan['TOP'], NT_TOP)
print('split: TOP=%d BOT=%d  (tracks avail T=%d B=%d)'%(len(chan['TOP']),len(chan['BOT']),NT_TOP,NT_BOT))

def track_yz(channel, t):
    """track index -> (y, horizontal layer). even idx -> M3, odd -> M2."""
    ys = TOP_Y if channel=='TOP' else BOT_Y
    layer = 'M3' if t%2==0 else 'M2'
    return ys[t//2], layer

def route(n):
    px, ix = n['px'], n['ix']; t=n['trk']
    y, hlay = track_yz(n['chan'], t)
    if n['chan']=='BOT':
        # macro pin (M2) down to track y, horizontal to ix, up M4 to IO
        vwire('M2', px, y-WIRE/2, MACRO_PIN_TOP)              # M2 from pin down to track
        if hlay=='M3': via_stack(['M2','M3'], px, y)
        hwire(hlay, px, ix, y)
        # up to M4 at ix
        if hlay=='M3': via_stack(['M3','M4'], ix, y)
        else: via_stack(['M2','M3','M4'], ix, y)
        vwire('M4', ix, y, IO_Y)
    else:  # TOP
        # macro pin (M2) down into the bottom MARGIN (clear of macro M3 fingers), stack up to M4,
        # then M4 vertical over the whole macro to the top track region, horizontal to ix, to IO.
        ystk = VIAUP_Y   # bottom margin, above BOT tracks (<=3.00), below macro (4.255), >=0.28 each
        vwire('M2', px, ystk, MACRO_PIN_TOP)
        via_stack(['M2','M3','M4'], px, ystk)
        vwire('M4', px, ystk, y)
        if hlay=='M3': via_stack(['M3','M4'], px, y)
        else: via_stack(['M2','M3','M4'], px, y)
        hwire(hlay, px, ix, y)
        if hlay=='M3': via_stack(['M3','M4'], ix, y)
        else: via_stack(['M2','M3','M4'], ix, y)
        vwire('M4', ix, y, IO_Y)

for n in nets: route(n)

lib.write_gds('gds_src/%s.gds'%top.name)
print('wrote gds: macro + boundary + %d io pins + %d data nets routed'%(len(IOX),len(nets)))
