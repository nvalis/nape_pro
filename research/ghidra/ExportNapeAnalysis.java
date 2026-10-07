// Export disassembly, decompiler output, and references for offline review.
// @category Nape

import java.io.File;
import java.io.PrintWriter;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

public class ExportNapeAnalysis extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Pass an output directory");
        File output = new File(args[0]);
        output.mkdirs();
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter index = new PrintWriter(new File(output, "functions.tsv"));
             PrintWriter c = new PrintWriter(new File(output, "decompiled.c"));
             PrintWriter asm = new PrintWriter(new File(output, "disassembly.txt"));
             PrintWriter refs = new PrintWriter(new File(output, "references.tsv"));
             PrintWriter blocks = new PrintWriter(new File(output, "memory.tsv"))) {
            index.println("address\tname\tbytes\tdecompiled");
            refs.println("from\tto\ttype\tfunction");
            blocks.println("name\tstart\tend\tinitialized\texecutable");
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                blocks.printf("%s\t%s\t%s\t%s\t%s%n", block.getName(), block.getStart(),
                    block.getEnd(), block.isInitialized(), block.isExecute());
            }
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            int count = 0;
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                boolean completed = result.decompileCompleted() && result.getDecompiledFunction() != null;
                index.printf("%s\t%s\t%d\t%s%n", function.getEntryPoint(), function.getName(),
                    function.getBody().getNumAddresses(), completed);
                c.printf("\n/* %s %s */\n", function.getEntryPoint(), function.getName());
                if (completed) c.println(result.getDecompiledFunction().getC());
                else c.printf("/* decompile failed: %s */%n", result.getErrorMessage());
                asm.printf("\n; %s %s%n", function.getEntryPoint(), function.getName());
                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    asm.printf("%s  %s%n", instruction.getAddress(), instruction);
                    for (Reference reference : instruction.getReferencesFrom()) {
                        refs.printf("%s\t%s\t%s\t%s%n", reference.getFromAddress(),
                            reference.getToAddress(), reference.getReferenceType(), function.getName());
                    }
                }
                count++;
            }
            println("Exported " + count + " functions to " + output);
        } finally {
            decompiler.dispose();
        }
    }
}
