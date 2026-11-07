// Print bounded PowerPC disassembly for address/byte-count argument pairs.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.UnknownInstructionException;

public class DumpPpcRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0 || args.length % 2 != 0) {
            throw new IllegalArgumentException("Expected pairs: hexadecimal-address byte-count");
        }
        PseudoDisassembler decoder = new PseudoDisassembler(currentProgram);
        for (int i = 0; i < args.length; i += 2) {
            Address start = toAddr(Long.decode(args[i]));
            int length = Integer.decode(args[i + 1]);
            if (length <= 0 || length > 65536 || length % 4 != 0) {
                throw new IllegalArgumentException("Byte count must be a multiple of 4 in 4..65536");
            }
            println("RANGE " + start + " bytes=" + length);
            for (int offset = 0; offset < length; offset += 4) {
                monitor.checkCancelled();
                Address address = start.add(offset);
                int word = currentProgram.getMemory().getInt(address);
                String decoded;
                try {
                    var instruction = decoder.disassemble(address);
                    decoded = instruction == null ? "<data>" : instruction.toString();
                } catch (UnknownInstructionException e) {
                    decoded = "<data>";
                }
                println(address + " " + String.format("%08x", word) + " " +
                    decoded);
            }
        }
    }
}
