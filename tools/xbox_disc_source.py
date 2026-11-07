"""Read archive members directly from an Xbox ISO, without staging split chunks."""
from pathlib import Path
from xdvdfs import open_image, walk, SECTOR, ATTR_DIR


class ISOReader:
    def __init__(self,image,offset,length):
        self.stream=image.open('rb');self.offset=offset;self.length=length;self.position=0
    def __enter__(self):return self
    def __exit__(self,*args):self.stream.close()
    def seek(self,offset,whence=0):
        position=offset if whence==0 else self.position+offset if whence==1 else self.length+offset
        if not 0<=position<=self.length:raise ValueError('ISO member seek exceeds extent')
        self.position=position;return position
    def read(self,size=-1):
        size=self.length-self.position if size<0 else min(size,self.length-self.position)
        self.stream.seek(self.offset+self.position)
        value=self.stream.read(size);self.position+=len(value);return value


class ISOMember:
    def __init__(self,source,name):self.source=source;self.name=name
    def __truediv__(self,name):return ISOMember(self.source,self.name+'/'+name)
    def is_file(self):return self.name.casefold() in self.source.members
    def open(self,mode='rb'):
        if mode!='rb':raise ValueError('Xbox ISO is read-only')
        offset,length=self.source.members[self.name.casefold()]
        return ISOReader(self.source.image,offset,length)


class XboxISO:
    def __init__(self,image:Path):
        self.image=image;self.members={}
        f,base,root,size=open_image(image)
        try:
            for name,sector,length,attributes in walk(f,base,root,size):
                if not attributes&ATTR_DIR:
                    if name.casefold() in self.members:raise ValueError('Duplicate Xbox ISO member')
                    self.members[name.casefold()]=(base+sector*SECTOR,length)
        finally:f.close()
        if 'default.xex' not in self.members or '0a' not in self.members:raise ValueError('Xbox game ISO lacks default.xex/0A')
    def __truediv__(self,name):return ISOMember(self,name)
