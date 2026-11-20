// Read-only Xbox UI string/xref research. Never changes program or game data.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
public class FindPresentationMenu extends GhidraScript {
 public void run() throws Exception {
  var memory=currentProgram.getMemory();var functions=currentProgram.getFunctionManager();
  var decompiler=new DecompInterface();decompiler.openProgram(currentProgram);var shown=new HashSet<String>();
  try{for(String term:getScriptArgs())for(boolean wide:new boolean[]{false,true}){
   byte[] pattern=term.getBytes(wide?StandardCharsets.UTF_16BE:StandardCharsets.US_ASCII);int hits=0;
   for(var block:memory.getBlocks()){
    if(!block.isInitialized())continue;var cursor=block.getStart();
    while(cursor.compareTo(block.getEnd())<=0 && hits<24){
     monitor.checkCancelled();var found=memory.findBytes(cursor,block.getEnd(),pattern,null,true,monitor);if(found==null)break;
     println("STRING "+term+" wide="+wide+" at="+found);hits++;
     var refs=currentProgram.getReferenceManager().getReferencesTo(found);int n=0;
     while(refs.hasNext() && n++<16){var ref=refs.next();var from=ref.getFromAddress();var f=functions.getFunctionContaining(from);println(" XREF "+from+" type="+ref.getReferenceType()+" function="+(f==null?"unknown":f.getName()+"@"+f.getEntryPoint()));
      if(f!=null && shown.add(f.getEntryPoint().toString()) && f.getBody().getNumAddresses()<12000){var result=decompiler.decompileFunction(f,30,monitor);if(result.decompileCompleted() && result.getDecompiledFunction()!=null)println(result.getDecompiledFunction().getC());}
     }
     cursor=found.add(pattern.length);
    }
   }
  }}finally{decompiler.dispose();}
 }
}
