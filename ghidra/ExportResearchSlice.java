// Bounded research export of initialized Xbox program memory; read-only.
// @category CH2K8
import ghidra.app.script.GhidraScript;
import java.nio.file.Files;
import java.nio.file.Path;
public class ExportResearchSlice extends GhidraScript {
 public void run() throws Exception {
  var a=getScriptArgs();if(a.length!=3)throw new IllegalArgumentException("ADDRESS SIZE OUTPUT");
  int size=Integer.decode(a[1]);if(size<=0 || size>0x4000000)throw new IllegalArgumentException("Size bound");
  byte[] data=new byte[size];int n=0;long start=Long.decode(a[0]);
  for(var block:currentProgram.getMemory().getBlocks()){
   if(!block.isInitialized())continue;long lo=Math.max(start,block.getStart().getOffset()),hi=Math.min(start+size,block.getEnd().getOffset()+1);
   if(hi<=lo)continue;int length=(int)(hi-lo);byte[] part=new byte[length];int read=currentProgram.getMemory().getBytes(toAddr(lo),part);
   System.arraycopy(part,0,data,(int)(lo-start),read);n+=read;println("BLOCK "+block.getName()+" "+Long.toHexString(lo)+" bytes="+read);
  }
  Files.write(Path.of(a[2]),data);println("EXPORTED "+a[0]+" bytes="+n);
 }
}
