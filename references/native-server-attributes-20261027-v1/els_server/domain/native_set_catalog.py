"""Read current-version KIM set records using the original 6DB6A0 layout.

Raw offsets/unknown fields are retained. This supplies definitions, not worn
item eligibility or effect math. Refuse foreign formats and malformed tables.
"""
import bisect,struct

class SetCatalog:
    def __init__(self,blob):
        if type(blob) is not bytes or len(blob)<16:raise ValueError('KIM bytes required')
        magic,version,items,sets=struct.unpack_from('<4I',blob)
        if magic!=0x204d494b or version!=0x1201:raise ValueError('unsupported KIM version')
        base=16+items*236
        if base+sets*36>len(blob):raise ValueError('truncated KIM index')
        self.blob=blob;self.item_count=items;self.base=base;self.count=sets
        self.ids=struct.unpack_from('<'+'I'*sets,blob,base)
        if any(a>=b for a,b in zip(self.ids,self.ids[1:])):raise ValueError('unordered set index')
        self.records={}
        for i,key in enumerate(self.ids):
            offset=base+sets*4+i*32
            raw=struct.unpack_from('<8I',blob,offset)
            if raw[0]!=key:raise ValueError('set record/index mismatch')
            ordinary=self._table(raw[4],2)
            qualified=self._table(raw[7],3,signed_first=True) if raw[7] else None
            if any(a[0]>b[0] for a,b in zip(ordinary,ordinary[1:])):raise ValueError('unordered thresholds')
            self.records[key]=dict(id=key,offset=offset,raw_dwords=raw,
                level_override=raw[1],category=raw[5],activation_required=bool(raw[6]),
                ordinary=ordinary,qualified=qualified)
    def _table(self,offset,width,signed_first=False):
        if not offset:return ()
        if not 16<=offset<=len(self.blob)-4:raise ValueError('table offset outside KIM')
        n=struct.unpack_from('<I',self.blob,offset)[0]
        if n>1024 or offset+4+n*width*4>len(self.blob):raise ValueError('truncated or excessive table')
        rows=[]
        for i in range(n):
            row=list(struct.unpack_from('<'+'I'*width,self.blob,offset+4+i*width*4))
            if signed_first and row[0]>=2**31:row[0]-=2**32
            rows.append(tuple(row))
        return tuple(rows)
    def lookup_offset(self,key):
        if type(key) is not int or not 0<=key<2**32:raise ValueError('uint32 set ID required')
        if not key:return None
        index=bisect.bisect_left(self.ids,key)
        return self.base+self.count*4+index*32 if index<self.count and self.ids[index]==key else None
