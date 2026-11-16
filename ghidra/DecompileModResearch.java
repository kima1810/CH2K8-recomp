// Decompile already identified Xbox entry points without changing the database.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
public class DecompileModResearch extends GhidraScript {
 public void run() throws Exception {var d=new DecompInterface();d.openProgram(currentProgram);try{
  for(String value:getScriptArgs()){
   var address=toAddr(Long.decode(value));var f=currentProgram.getFunctionManager().getFunctionAt(address);
   println("FUNCTION "+address+" "+(f==null?"UNDEFINED":f.getName()));
   if(f!=null){var r=d.decompileFunction(f,40,monitor);if(r.decompileCompleted() && r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());else println("FAILED "+r.getErrorMessage());}
  }
 }finally{d.dispose();}}
}
