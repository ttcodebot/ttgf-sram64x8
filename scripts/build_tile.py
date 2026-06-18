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
PRBND = (0,0)    # gf180 PR_bndry is layer 0/0 (precheck KLayout check + boundary check use it)

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

# macro power rails (tile coords), parsed from the macro LEF, for net-verified PDN landings
import re as _re
def _macro_pwr(pin, layer):
    blk=_re.search(r'PIN %s\b.*?END %s'%(pin,pin), open('macro/%s/%s.lef'%(MACRO,MACRO)).read(), _re.S).group(0)
    out=[]; lay=None
    for line in blk.splitlines():
        m=_re.search(r'LAYER (\w+)', line);  lay=m.group(1) if m else lay
        r=_re.search(r'RECT ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)', line)
        if r and lay==layer: out.append(tuple(map(float,r.groups())))
    return [(a+MX,b+MY,c+MX,d+MY) for a,b,c,d in out]
PWR = {(p,l): _macro_pwr(p,l) for p in ('VDD','VSS') for l in ('Metal1','Metal2','Metal3')}
def _covers(rl, x, y):
    return any(r[0]+0.2<=x<=r[2]-0.2 and r[1]-0.01<=y<=r[3]+0.01 for r in rl)
def inside(pin, layer, x, y, half=0.205):
    """True if a 2*half square via patch at (x,y) lies fully inside ONE macro pin/layer rect
    (so it merges cleanly with no <0.28 edge to a neighbour shape)."""
    return any(r[0]+half<=x<=r[2]-half and r[1]+half<=y<=r[3]-half for r in PWR[(pin,layer)])
def land_y(pin, layer, x, ylo, yhi):
    """y in [ylo,yhi] where a via patch at (x,y) lies fully inside a macro pin/layer finger."""
    for r in PWR[(pin,layer)]:
        if r[0]+0.21<=x<=r[2]-0.21:
            y=max(r[1]+0.21, min((r[1]+r[3])/2, yhi));
            if ylo<=y<=yhi and r[1]+0.21<=y<=r[3]-0.21: return round(y,3)
    return None

# TT 1x1 I/O pin x-positions (tile coords), all Metal4 at IO_Y
IOX = {
 'clk':331.24,'ena':338.52,'rst_n':323.96,
 **{f'ui_in[{i}]':x for i,x in enumerate([316.68,309.40,302.12,294.84,287.56,280.28,273.00,265.72])},
 **{f'uio_in[{i}]':x for i,x in enumerate([258.44,251.16,243.88,236.60,229.32,222.04,214.76,207.48])},
 **{f'uo_out[{i}]':x for i,x in enumerate([200.20,192.92,185.64,178.36,171.08,163.80,156.52,149.24])},
 **{f'uio_out[{i}]':x for i,x in enumerate([141.96,134.68,127.40,120.12,112.84,105.56,98.28,91.00])},
 **{f'uio_oe[{i}]':x for i,x in enumerate([83.72,76.44,69.16,61.88,54.60,47.32,40.04,32.76])},
}

lib = gdstk.Library(name='ttsram', unit=1e-6, precision=1e-9)  # 1nm DBU (gf180 standard; 0.005um grid = 5 DBU)
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
PIN_W=0.30; PIN_H=1.0   # MUST match the frame DEF pin dims (Metal4 -300 -1000 .. 300 1000 DBU)
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

# ---------- PDN: connect the stripes to the macro power ring at many points ----------
# The macro carries a full-perimeter power ring: VSS on Metal1 (left rail x~24, full-width top
# y153.5..155.5 and bottom y5.2..7.3 rails) and VDD on Metal2/Metal3 (left rail x~25, top rails,
# plus Metal3 fingers reaching top AND bottom edges across the width). We:
#   (a) tie the left VGND stripe to the macro VSS Metal3 left rail at many y (M3 passes UNDER the
#       VDPWR stripe; merges with macro VSS M3 on net-verified clean rows);
#   (b) tie the left VDPWR stripe to the macro VDD Metal2/Metal3 left rail at many y;
#   (c) run several real M4 VDPWR straps OVER the macro in the wide signal-free gaps, each viaing
#       down onto a VDD Metal3 finger at the macro's TOP and BOTTOM edges (VSS is absent at those
#       columns, so no short). All straps share the VDPWR net through the macro VDD ring + are
#       declared as VDPWR pins so the chip M5 grid also feeds them directly.
PWR_STRAP_W = 1.20
vgnd_pin_rects = [(3.0, PWR_Y0, 7.0, PWR_Y1)]
vdpwr_pin_rects = [(10.0, PWR_Y0, 14.0, PWR_Y1)]

# (a) VGND left taps: only where x22.7..24.2 is solidly inside the macro VSS Metal3 left rail at
#     yc +/- 0.2 (clean merge, no edge to a neighbour), and no VDD M3 anywhere near.
def connect_vgnd_left(yc):
    if all(inside('VSS','Metal3', x, yc) for x in (23.0,23.5,24.0)) and \
       not any(_covers(PWR[('VDD','Metal3')], x, y) for x in (22.8,23.5,24.2) for y in (yc-0.3,yc+0.3)):
        via('V3', 5.0, yc); hwire('M3', 5.0, 24.2, yc); return True
    return False

# (b) VDPWR left taps: via down onto a VDD Metal3 finger near the left rail, gated fully-inside.
def connect_vdpwr_left(yc):
    for x in (25.23, 25.0, 25.5, 24.8):
        if inside('VDD','Metal3', x, yc) and not _covers(PWR[('VSS','Metal3')], x, yc):
            hwire('M4', 12.0, x+0.45, yc); via('V3', x, yc); return True
    return False

ng=nv=0
for yc in [round(11+5*k,2) for k in range(29)]:           # y 11..151 step 5
    if PWR_Y0+1<yc<PWR_Y1-1:
        if connect_vgnd_left(yc): ng+=1
        if connect_vdpwr_left(yc): nv+=1
print('left taps: VGND=%d VDPWR=%d'%(ng,nv))

# (c) over-macro M4 VDPWR straps: scan each signal-free gap for a column where a VDD Metal3 finger
#     fully contains the via patch at BOTH the bottom (y~5.8) and top (y~154) edges, with VSS absent.
def strap_col(xlo, xhi):
    x=xlo+1.1                                              # clear the gap-edge signal M4 (half 0.6 + 0.28)
    while x<xhi-1.1:
        yb=land_y('VDD','Metal3', x, 4.3, 8.0); yt=land_y('VDD','Metal3', x, 152.0, 156.5)
        if yb and yt and inside('VDD','Metal3',x,yb) and inside('VDD','Metal3',x,yt) \
           and not _covers(PWR[('VSS','Metal3')],x,5.8) and not _covers(PWR[('VSS','Metal3')],x,154.5):
            return round(x,3), yb, yt
        x+=0.5
    return None
ns=0
for (xlo,xhi) in [(143,156),(171,200),(200,213),(222,236),(237,273),(273,308),(316,331)]:
    r=strap_col(xlo,xhi)
    if r:
        x,yb,yt=r
        vwire('M4', x, yb, yt, w=PWR_STRAP_W)
        via('V3', x, yb); via('V3', x, yt)
        vdpwr_pin_rects.append((x-PWR_STRAP_W/2, yb, x+PWR_STRAP_W/2, yt)); ns+=1
print('over-macro VDPWR straps: %d'%ns)

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

# ---------- control signals + ties ----------
# The SRAM controls are all ACTIVE-LOW, so we expose them directly (no inverters):
#   GWEN <- ui_in[6]  (active-low write enable: 0 = write this cycle, 1 = read)
#   CEN  = 0          (chip always enabled)            -> tie to VGND
#   WEN[0:7] = 0      (all 8 bits write when GWEN=0)   -> tie to VGND
# CEN/WEN ties land on the macro's own full-width VSS Metal1 bottom rail (tile y~5.24..7.255),
# directly beneath each Metal2 control pin, via a single Via1 (net-verified VSS landings).
def tie_pin_to_vss(name):
    x = pin_xc(name)
    vwire('M2', x, 5.0, MACRO_PIN_TOP)     # ensure the pin M2 overlaps the VSS M1 rail region
    via('V1', x, 6.2)                      # Via1: pin Metal2 -> macro VSS Metal1 rail
for nm in ['CEN'] + [f'WEN[{i}]' for i in range(8)]:
    tie_pin_to_vss(nm)

# GWEN routed from ui_in[6] on a dedicated Metal1 lane in the via-up band (y=VIAUP_Y): Metal1 is
# unused by the data routing (M2/M3/M4 only), so it crosses everything without shorting.
def route_control(io_name, macro_pin):
    iox = IOX[io_name]; px = pin_xc(macro_pin); y = VIAUP_Y
    vwire('M4', iox, y, IO_Y)               # IO (M4) down to the band
    via_stack(['M2','M3','M4'], iox, y)     # M4 -> M3 -> M2
    via('V1', iox, y)                       # M2 -> M1
    hwire('M1', iox, px, y)                 # permutation on M1
    via('V1', px, y)                        # M1 -> M2 at the macro pin column
    vwire('M2', px, y, MACRO_PIN_TOP)       # M2 up to the macro pin
route_control('ui_in[6]', 'GWEN')

# ---------- tie unused outputs uio_out[7:0], uio_oe[7:0] = 0 (to VGND) ----------
# Each is a frame Metal4 pin on the top edge; drop an M4 vertical to the via-up band and join a
# Metal1 VGND collector that runs back to the VGND stripe. Metal1 is unused by the data routing,
# and the tie columns clear the data M4 via-ups (nearest is 0.81um away).
tie_outs = [f'uio_out[{i}]' for i in range(8)] + [f'uio_oe[{i}]' for i in range(8)]
tie_xs = sorted(IOX[n] for n in tie_outs)
hwire('M1', 4.8, tie_xs[-1], VIAUP_Y)                 # M1 VGND collector along the band
via_stack(['M1','M2','M3','M4'], 5.0, VIAUP_Y)        # collector -> VGND M4 stripe (x3..7)
# Data/control M2 columns to keep the tie via-stacks' M2 patches clear of (>=0.68um center-center).
m2_cols = sorted(set([n['px'] for n in nets] + [pin_xc('GWEN')]))
def clear_via_x(x0):
    for off in (0, -0.7, 0.7, -1.2, 1.2, -1.8, 1.8):
        if all(abs(x0+off-m) > 0.68 for m in m2_cols): return x0+off
    return x0
for n in tie_outs:
    x = IOX[n]; vdx = clear_via_x(x)
    vwire('M4', x, VIAUP_Y, IO_Y)                     # M4 down from the pin
    if abs(vdx-x) > 1e-3: hwire('M4', x, vdx, VIAUP_Y)  # short M4 jog to a clear via column
    via_stack(['M2','M3','M4'], vdx, VIAUP_Y)         # M4 -> M2 at the clear column
    via('V1', vdx, VIAUP_Y)                           # M2 -> M1 collector

# Extra VGND robustness: link the VGND Metal1 collector (y=VIAUP_Y) UP to the macro's full-width
# VSS Metal1 bottom rail (y5.24..7.255) at many columns between the tie pins. Metal1->Metal1 merge
# (no via), placed at tie-pin midpoints so the link clears every tie's M1 via pad. The bottom rail
# is solid VSS across the macro width, so each link is a verified VGND<->VSS connection.
# narrow macro VSS M1 features (substrate taps) sit just below the rail (~y5.0..5.24); a link that
# comes within 0.28 of one (without overlapping) is an M1.2a, so skip columns near such features.
# Any macro M1 in the band the link traverses below the rail (y4.3..5.24); skip a column unless
# the link either clears every such shape by >=0.28 or sits fully inside one (clean merge).
_m1_band = [r for r in (PWR[('VSS','Metal1')]+PWR[('VDD','Metal1')]) if r[1]<5.24 and r[3]>4.3]
def m1_link_clear(x):
    for r in _m1_band:
        near = (r[0]-0.48) < x < (r[2]+0.48)
        covers = (r[0]+0.2) <= (x-0.2) and (x+0.2) <= (r[2]-0.2)
        if near and not covers: return False
    return True
mids = [round((tie_xs[i]+tie_xs[i+1])/2,3) for i in range(len(tie_xs)-1)]
nvg=0
for x in mids:
    if _covers(PWR[('VSS','Metal1')], x, 6.0) and m1_link_clear(x):
        vwire('M1', x, VIAUP_Y, 6.4); vgnd_pin_rects.append((x-0.2, VIAUP_Y, x+0.2, 6.4)); nvg+=1
print('VGND bottom-rail links: %d'%nvg)

lib.write_gds('src/%s.gds'%top.name)
print('wrote gds: macro + boundary + %d io pins + %d data nets routed'%(len(IOX),len(nets)))

# ---------- LEF (abstract: top-edge Metal4 signal pins + left-edge Metal4 power stripes) ----------
def pin_dir(name):
    base = name.split('[')[0]
    return {'uo_out':'OUTPUT','uio_out':'OUTPUT','uio_oe':'OUTPUT'}.get(base, 'INPUT')
def lef_pin(name, x):
    return ("  PIN %s\n    DIRECTION %s ;\n    USE SIGNAL ;\n    PORT\n      LAYER Metal4 ;\n"
            "        RECT %.3f %.3f %.3f %.3f ;\n    END\n  END %s\n"
            % (name, pin_dir(name), x-PIN_W/2, IO_Y-PIN_H/2, x+PIN_W/2, IO_Y+PIN_H/2, name))
def lef_pwr(name, rects, use):
    ports = "".join("      LAYER Metal4 ;\n        RECT %.3f %.3f %.3f %.3f ;\n"%r for r in rects)
    return "  PIN %s\n    DIRECTION INOUT ;\n    USE %s ;\n    PORT\n%s    END\n  END %s\n" % (name, use, ports, name)
with open('lef/%s.lef'%top.name,'w') as f:
    f.write('VERSION 5.7 ;\nBUSBITCHARS "[]" ;\nDIVIDERCHAR "/" ;\n\n')
    f.write('MACRO %s\n  CLASS BLOCK ;\n  FOREIGN %s 0 0 ;\n  ORIGIN 0 0 ;\n  SIZE %.3f BY %.3f ;\n'
            % (top.name, top.name, TILE_W, TILE_H))
    for nm in IOX: f.write(lef_pin(nm, IOX[nm]))
    # Only the full-height left stripes are declared as power PINS: the TT pin check requires each
    # power port RECT to be >=0.8um wide AND reach within 10um of the top edge (frame connects power
    # at the top). The over-macro straps + Metal1 links are internal PDN geometry on the same net
    # (tied to the macro VDD/VSS ring, which the stripes feed) -> they don't need to be pins.
    f.write(lef_pwr('VGND',  [(3.0,  PWR_Y0, 7.0,  PWR_Y1)], 'GROUND'))
    f.write(lef_pwr('VDPWR', [(10.0, PWR_Y0, 14.0, PWR_Y1)], 'POWER'))
    f.write('END %s\n\nEND LIBRARY\n'%top.name)
print('wrote lef/%s.lef'%top.name)
