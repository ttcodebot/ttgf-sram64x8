# Custom PDN configuration for the gf180 64x8 SRAM macro integration.
#
# The macro exposes its VDD/VSS power pins on Metal1/Metal2/Metal3, all clustered as
# (mostly full-macro-width) rails along the macro's TOP edge. The macro distributes power
# internally; externally it just needs the tile's Metal4 PDN straps to drop vias onto those
# top-edge power rails. PDN vertical layer for gf180 (cmos5l) = Metal4, so we connect the
# Metal4 straps DOWN to the macro's Metal3/Metal2 power pins via a dedicated macro PDN grid.

source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd

        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }

    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd

        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary

# Allow unrepaired channels — Metal1 followpins near macro halo have no stdcells
pdn::allow_repair_channels true

# Stdcell grid
define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins $::env(PDN_VERTICAL_LAYER)

add_pdn_stripe \
    -grid stdcell_grid \
    -layer $::env(PDN_VERTICAL_LAYER) \
    -width $::env(PDN_VWIDTH) \
    -pitch $::env(PDN_VPITCH) \
    -offset $::env(PDN_VOFFSET) \
    -spacing $::env(PDN_VSPACING) \
    -starts_with POWER -extend_to_core_ring

# Standard cell rails on Metal1
if { $::env(PDN_ENABLE_RAILS) == 1 } {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_RAIL_LAYER) \
        -width $::env(PDN_RAIL_WIDTH) \
        -followpins

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_RAIL_LAYER) $::env(PDN_VERTICAL_LAYER)"
}

# SRAM macro grid: connect the Metal4 core/stdcell straps down onto the macro's top-edge
# power pins. The macro's Metal2 rails are full-macro-width for both nets (guaranteed strap
# overlap); Metal3 is the topmost pin layer. Connecting Metal4 to both gives reliable vias.
define_pdn_grid \
    -macro \
    -default \
    -name macro \
    -starts_with POWER \
    -halo "$::env(PDN_HORIZONTAL_HALO) $::env(PDN_VERTICAL_HALO)"

add_pdn_connect \
    -grid macro \
    -layers "Metal3 Metal4"

add_pdn_connect \
    -grid macro \
    -layers "Metal2 Metal4"
