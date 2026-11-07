// Export only the exact r12/rlwinm/lwzx/CTR inline absolute-table idiom.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;

public class ExportInlineSwitches extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1 || !currentProgram.getLanguage().isBigEndian()) {
            throw new IllegalArgumentException("Expected an output TOML path and a big-endian program");
        }
        MemoryBlock text = currentProgram.getMemory().getBlock(".text");
        if (text == null) throw new IllegalArgumentException("No .text block");
        long start = text.getStart().getOffset(), end = text.getEnd().getOffset();
        var memory = currentProgram.getMemory();
        var decoder = new PseudoDisassembler(currentProgram);
        int exported = 0;
        try (PrintWriter out = new PrintWriter(Files.newBufferedWriter(Path.of(args[0]), StandardCharsets.UTF_8))) {
            out.println("# Exact inline absolute tables; targets validated within .text.");
            for (long site = start + 20; site + 4 <= end; site += 4) {
                if ((site & 4095) == 0) monitor.checkCancelled();
                if (memory.getInt(toAddr(site)) != 0x4e800420) continue;
                int lis = memory.getInt(toAddr(site - 20));
                int addi = memory.getInt(toAddr(site - 16));
                int scale = memory.getInt(toAddr(site - 12));
                if ((lis & 0xffff0000) != 0x3d800000 || (addi & 0xffff0000) != 0x398c0000 ||
                    (scale & ~0x03e00000) != 0x5400103a ||
                    memory.getInt(toAddr(site - 8)) != 0x7c0c002e ||
                    memory.getInt(toAddr(site - 4)) != 0x7c0903a6) continue;
                long table = (((long)(lis & 0xffff) << 16) + (short)addi) & 0xffffffffL;
                if (table != site + 4) continue;
                var labels = new ArrayList<Long>();
                long cursor = table, firstCase = end + 1;
                while (labels.size() < 4096 && cursor + 3 <= end && cursor < firstCase) {
                    long target = Integer.toUnsignedLong(memory.getInt(toAddr(cursor)));
                    if (target < table || target > end || (target & 3) != 0) break;
                    labels.add(target);
                    firstCase = Math.min(firstCase, target);
                    cursor += 4;
                }
                // The pointer array must end exactly at its earliest case body.
                if (labels.isEmpty() || cursor != firstCase) continue;
                boolean valid = true;
                for (long target : labels) {
                    try {
                        if (decoder.disassemble(toAddr(target)) == null) valid = false;
                    } catch (Exception e) { valid = false; }
                    if (!valid) break;
                }
                if (!valid) continue;
                out.printf("%n[[switch_tables]]%naddress = 0x%08X%nregister = %d%nlabels = [", site, (scale >>> 21) & 31);
                for (int i = 0; i < labels.size(); i++) {
                    if (i != 0) out.print(", ");
                    out.printf("0x%08X", labels.get(i));
                }
                out.println("]");
                exported++;
            }
        }
        println("Exported " + exported + " validated inline switch tables");
    }
}
