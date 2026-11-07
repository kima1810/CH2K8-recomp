// Read-only audit of raw data pointers missing from generated dispatch.
// Candidates are evidence only, never automatic function registrations.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;
import java.io.*;

public class ExportUnregisteredDataCallbacks extends GhidraScript {
    public void run() throws Exception {
        String[] args=getScriptArgs();
        if(args.length!=2)throw new IllegalArgumentException("registry.cpp report.tsv");
        Set<Long> registered=new HashSet<>();
        Matcher matches=Pattern.compile("\\{ 0x([0-9A-Fa-f]{8}),").matcher(Files.readString(Path.of(args[0])));
        while(matches.find())registered.add(Long.parseLong(matches.group(1),16));
        Map<Long,List<Long>> refs=new TreeMap<>();
        var mem=currentProgram.getMemory();var fm=currentProgram.getFunctionManager();
        for(var block:mem.getBlocks()) {
            if(!block.isInitialized()||block.isExecute())continue;
            long start=(block.getStart().getOffset()+3)&~3L,end=block.getEnd().getOffset();
            for(long offset=start;offset+3<=end;offset+=4) {
                monitor.checkCancelled();long target=Integer.toUnsignedLong(mem.getInt(toAddr(offset)));
                if((target&3)!=0||registered.contains(target))continue;
                var address=toAddr(target);var code=mem.getBlock(address);
                if(code==null||!code.isExecute())continue;
                refs.computeIfAbsent(target,k->new ArrayList<>()).add(offset);
            }
        }
        try(var out=new PrintWriter(Files.newBufferedWriter(Path.of(args[1])))) {
            out.println("entry\tend\tbytes\trefs\tfirst_reference\tname\twords");
            for(var entry:refs.entrySet()) {
                var f=fm.getFunctionAt(toAddr(entry.getKey()));
                out.printf("%08X\t%08X\t%d\t%d\t%08X\t%s\t",entry.getKey(),f==null?0:f.getBody().getMaxAddress().getOffset()+1,f==null?0:f.getBody().getNumAddresses(),entry.getValue().size(),entry.getValue().get(0),f==null?"unanalyzed":f.getName());
                for(int i=-1;i<8;i++)out.printf("%08X ",mem.getInt(toAddr(entry.getKey()+i*4)));
                out.println();
            }
        }
        println("Unregistered raw code-pointer candidates: "+refs.size());
    }
}
