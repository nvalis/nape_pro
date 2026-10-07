// Seed protocol functions missed by automatic function discovery.
// @category Nape

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.SourceType;

public class AnnotateNape130 extends GhidraScript {
    @Override
    public void run() throws Exception {
        entry(0x04048f0cL, "launcher_raw_hid_dispatch");
        entry(0x04048d20L, "launcher_misc_dispatch");
        entry(0x0404c898L, "nape_subcommand_dispatch");
        entry(0x0404bcacL, "nape_save_all_records_candidate");
        entry(0x04050b00L, "settings_save_one_candidate");
        entry(0x0404c598L, "nape_effective_pointer_dpi");
        entry(0x0404c62cL, "nape_scroll_mode_dpi_candidate");
        entry(0x0404c7fcL, "nape_effective_orientation");
        entry(0x0404c80cL, "nape_set_effective_orientation");
        entry(0x0011d738L, "zmk_effective_layer_candidate");
        entry(0x0011d95cL, "zmk_default_layer_candidate");
        createLabel(toAddr(0x001077d0L), "nape_settings_27_bytes", true, SourceType.USER_DEFINED);
        createLabel(toAddr(0x00109928L), "nape_combos_241_bytes", true, SourceType.USER_DEFINED);
        createLabel(toAddr(0x00109920L), "nape_gesture_8_bytes", true, SourceType.USER_DEFINED);
        createLabel(toAddr(0x0010984cL), "nape_tapholds_211_bytes", true, SourceType.USER_DEFINED);
        // Remove a label from the initial exploratory import; VTOR uses flash.
        for (var symbol : currentProgram.getSymbolTable().getSymbols(toAddr(0x0011be00L))) {
            if (symbol.getName().equals("runtime_vector_table")) symbol.delete();
        }
    }

    private void entry(long value, String name) throws Exception {
        Address address = toAddr(value);
        if (getInstructionAt(address) == null) disassemble(address);
        if (getFunctionAt(address) == null) createFunction(address, name);
        else getFunctionAt(address).setName(name, SourceType.USER_DEFINED);
        currentProgram.getSymbolTable().addExternalEntryPoint(address);
    }
}
