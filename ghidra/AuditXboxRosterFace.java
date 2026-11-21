// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

public class AuditXboxRosterFace extends GhidraScript {
    @Override
    public void run() throws Exception {
        try (PrintWriter out = new PrintWriter(getScriptArgs()[0])) {
            for (long location : new long[]{0x82004504L, 0x820044dcL, 0x82000d78L,
                    0x82004500L, 0x820043d0L, 0x820009f0L, 0x82000a00L}) {
                var address = toAddr(location);
                out.printf("constant %s float=%s double=%s%n", address,
                    Float.intBitsToFloat(currentProgram.getMemory().getInt(address)),
                    Double.longBitsToDouble(currentProgram.getMemory().getLong(address)));
            }
            var strings = new ArrayList<Long>();
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (block.isExecute() || !block.isInitialized()) continue;
                byte[] data = new byte[(int) block.getSize()];
                currentProgram.getMemory().getBytes(block.getStart(), data);
                String content = new String(data, StandardCharsets.ISO_8859_1);
                for (String needle : new String[]{"FaceGen_ApplyHeadMorphsToTexture", "facenormal%02d", "face%02d", "facegen_head", "facegen.iff"}) {
                    int position = content.indexOf(needle);
                    while (position >= 0) {
                        long location = block.getStart().add(position).getOffset();
                        out.printf("string %x %s%n", location, needle);
                        strings.add(location);
                        position = content.indexOf(needle, position + needle.length());
                    }
                }
            }
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (!block.isExecute() || !block.isInitialized()) continue;
                byte[] data = new byte[(int) block.getSize()];
                currentProgram.getMemory().getBytes(block.getStart(), data);
                for (int start = 0; start + 4 <= data.length; start += 4) {
                    int first = word(data, start);
                    if (first >>> 26 == 15 && (first >>> 16 & 31) == 0) {
                        int register = first >>> 21 & 31;
                        long high = (first & 0xffffL) << 16;
                        for (long address : strings) {
                            if ((address + 0x8000 & 0xffff0000L) != high) continue;
                            for (int site = start + 4; site + 4 <= data.length && site <= start + 48; site += 4) {
                                int next = word(data, site);
                                if (next >>> 26 != 14 || (next >>> 16 & 31) != register ||
                                        high + (short) next != address) continue;
                                var location = block.getStart().add(site);
                                var function = getFunctionContaining(location);
                                out.printf("string xref %s -> %x function=%s%n", location, address,
                                    function == null ? "unknown" : function.getEntryPoint());
                            }
                        }
                    }
                    if (first >>> 26 == 18 && (first & 2) == 0) {
                        int displacement = (first << 6) >> 6 & ~3;
                        var site = block.getStart().add(start);
                        long target = site.getOffset() + displacement;
                        if (target >= 0x84738710L && target <= 0x84738760L &&
                                (target & 15) == 0) {
                            var caller = getFunctionContaining(site);
                            out.printf("call %s -> %x function=%s%n", site, target,
                                caller == null ? "unknown" : caller.getEntryPoint());
                        }
                    }
                    int offset = first & 0xffff;
                    if (offset < 0xa0 || offset > 0xc0 || !access(first)) continue;
                    int base = first >>> 16 & 31;
                    if (base == 0 || base == 1) continue;
                    boolean second = false;
                    boolean third = false;
                    for (int site = start + 4; site + 4 <= data.length && site < start + 0x240; site += 4) {
                        int instruction = word(data, site);
                        if ((instruction >>> 16 & 31) != base || !access(instruction)) continue;
                        second |= (instruction & 0xffff) == offset + 50;
                        third |= (instruction & 0xffff) == offset + 80;
                    }
                    if (second && third) {
                        var address = block.getStart().add(start);
                        var function = getFunctionContaining(address);
                        out.printf("%s offset=%x base=r%d function=%s%n", address, offset, base,
                            function == null ? "unknown" : function.getEntryPoint());
                    }
                }
            }
        }
    }

    private int word(byte[] data, int position) {
        return (data[position] & 255) << 24 | (data[position + 1] & 255) << 16
            | (data[position + 2] & 255) << 8 | data[position + 3] & 255;
    }

    private boolean access(int instruction) {
        int opcode = instruction >>> 26;
        return opcode == 14 || opcode == 34 || opcode == 35 || opcode == 38 || opcode == 39;
    }
}
