// Prepare the published Nape Pro 1.3.0 image for static analysis.
// @category Nape

import java.math.BigInteger;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.PointerDataType;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class PrepareNape130 extends GhidraScript {
    private Address addr(long value) { return toAddr(value); }

    private void label(long value, String name) throws Exception {
        createLabel(addr(value), name, true, SourceType.USER_DEFINED);
    }

    private void entry(long value, String name) throws Exception {
        Address a = addr(value & ~1L);
        label(value & ~1L, name);
        if (getInstructionAt(a) == null) {
            currentProgram.getProgramContext().setValue(
                currentProgram.getRegister("TMode"), a, a, BigInteger.ONE);
            disassemble(a);
        }
        if (getFunctionAt(a) == null) createFunction(a, name);
        currentProgram.getSymbolTable().addExternalEntryPoint(a);
    }

    @Override
    public void run() throws Exception {
        // These mappings come from the startup memcpy calls at 0402d898
        // and 04067940, not from guessed chip addresses.
        if (getInt(addr(0x0402d1c8L)) != 0x0402d000 ||
            getInt(addr(0x0402d604L)) != 0x0402d859) {
            throw new IllegalArgumentException("Not the expected Nape 1.3.0 image");
        }
        MemoryBlock flash = currentProgram.getMemory().getBlock(addr(0x0402d000L));
        flash.setName("firmware_image");
        flash.setRead(true);
        flash.setWrite(false);
        flash.setExecute(true);

        // Create uninitialized RAM first; do not pretend this is a RAM dump.
        currentProgram.getMemory().createUninitializedBlock(
            "ram_before_data", addr(0x00100000L), 0xc00, false).setWrite(true);
        copy(0x00100c00L, 0x0406f814L, 0x19d0, "ram_data_a", false);
        copy(0x001025d0L, 0x040711e4L, 0x327c, "ram_data_b", false);
        currentProgram.getMemory().createUninitializedBlock(
            "ram_bss", addr(0x0010584cL), 0x143b4, false).setWrite(true);
        copy(0x00119c00L, 0x0402d8e8L, 0x11d90, "ram_code", true);
        copy(0x0012b990L, 0x0403f678L, 0x8e8, "ram_extra_a", false);
        copy(0x0012c278L, 0x0403ff60L, 0xbb8, "ram_extra_b", false);
        currentProgram.getMemory().createUninitializedBlock(
            "ram_tail", addr(0x0012ce30L), 0x131d0, false).setWrite(true);

        entry(0x0402d858L, "reset_handler");
        entry(0x0402d7f8L, "early_startup");
        entry(0x0402d898L, "copy_initialized_sections");
        entry(0x04067940L, "copy_ram_code_sections");
        entry(0x04053e1cL, "memcpy_candidate");
        entry(0x04053e94L, "memset_candidate");
        label(0x0402d600L, "image_vector_table");
        // VTOR points to the flash table at 0402d600; code begins at 0402d7f8.
        for (int index = 1; index < 126; index++) {
            Address slot = addr(0x0402d600L + index * 4L);
            long target = Integer.toUnsignedLong(getInt(slot));
            if ((target & 1) != 0 && currentProgram.getMemory().contains(addr(target & ~1L))) {
                if (getDataAt(slot) == null && getInstructionAt(slot) == null) {
                    createData(slot, new PointerDataType());
                }
                if (getFunctionAt(addr(target & ~1L)) == null) {
                    entry(target, "vector_" + index);
                }
            }
        }
        println("Prepared flash at 0402d000 and startup-derived RAM copies.");
    }

    private void copy(long destination, long source, int size, String name, boolean executable)
            throws Exception {
        byte[] bytes = getBytes(addr(source), size);
        MemoryBlock block = currentProgram.getMemory().createInitializedBlock(
            name, addr(destination), size, (byte) 0, monitor, false);
        currentProgram.getMemory().setBytes(addr(destination), bytes);
        block.setRead(true);
        block.setWrite(true);
        block.setExecute(executable);
        println(String.format("%s: %08x <- %08x, %x bytes", name, destination, source, size));
    }
}
