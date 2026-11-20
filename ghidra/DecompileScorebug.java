// Temporary function definitions are discarded by the read-only headless session.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import java.nio.file.Files;
import java.nio.file.Path;
public class DecompileScorebug extends GhidraScript {
 public void run() throws Exception {
  var args=getScriptArgs();var output=new StringBuilder();
  for(int i=1;i<args.length;i++){
   var a=toAddr(Long.decode(args[i]));
   if(getFunctionAt(a)==null){disassemble(a);createFunction(a,null);}
  }
  var d=new DecompInterface();d.openProgram(currentProgram);
  try{for(int i=1;i<args.length;i++){
   var a=toAddr(Long.decode(args[i]));var f=getFunctionAt(a);
   output.append("\nFUNCTION ").append(a).append("\n");
   if(f==null){output.append("UNDEFINED\n");continue;}
   var result=d.decompileFunction(f,40,monitor);
   output.append(result.decompileCompleted()?result.getDecompiledFunction().getC():result.getErrorMessage());
  }}finally{d.dispose();}
  Files.writeString(Path.of(args[0]),output.toString());
 }
}
