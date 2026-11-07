// Find raw big-endian guest-pointer words without changing the program.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class FindGuestPointers extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (String argument : getScriptArgs()) {
            long target = Long.decode(argument);
            byte[] bytes = ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN).putInt((int)target).array();
            println(String.format("TARGET %08X", target));
            var memory = currentProgram.getMemory();
            for (var block : memory.getBlocks()) {
                if (!block.isInitialized()) continue;
                var cursor = block.getStart();
                while (cursor.compareTo(block.getEnd()) <= 0) {
                    monitor.checkCancelled();
                    var found = memory.findBytes(cursor, block.getEnd(), bytes, null, true, monitor);
                    if (found == null) break;
                    println("REFERENCE " + found + " block=" + block.getName());
                    for (int offset = -16; offset <= 16; offset += 4) {
                        var address = found.add(offset);
                        if (block.contains(address) && block.contains(address.add(3))) {
                            println(address + " " + String.format("%08X", memory.getInt(address)));
                        }
                    }
                    cursor = found.add(4);
                }
            }
        }
    }
}
