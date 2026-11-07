"""Per-connection native DES key schedule; the existing wire format is unchanged."""
import hmac,secrets,struct,sys
from els_server.protocol.protocol_codec import ProtocolError,encode_frame

if sys.platform=='win32':
    import ctypes
    _P=ctypes.c_void_p;_U=ctypes.c_ulong
    _api=ctypes.WinDLL('bcrypt.dll')
    for _name,_args in {
        'BCryptOpenAlgorithmProvider':[ctypes.POINTER(_P),ctypes.c_wchar_p,ctypes.c_wchar_p,_U],
        'BCryptSetProperty':[_P,ctypes.c_wchar_p,_P,_U,_U],
        'BCryptGetProperty':[_P,ctypes.c_wchar_p,_P,_U,ctypes.POINTER(_U),_U],
        'BCryptGenerateSymmetricKey':[_P,ctypes.POINTER(_P),_P,_U,_P,_U,_U],
        'BCryptEncrypt':[_P,_P,_U,_P,_P,_U,_P,_U,ctypes.POINTER(_U),_U],
        'BCryptDestroyKey':[_P], 'BCryptCloseAlgorithmProvider':[_P,_U],
    }.items():
        _function=getattr(_api,_name);_function.argtypes=_args;_function.restype=ctypes.c_long

    def _checked(status):
        if status:raise OSError('Native frame cipher status %08x'%(status&0xffffffff))

    class _Cipher:
        def __init__(self,key):
            self.algorithm=_P();self.key=_P()
            try:
                _checked(_api.BCryptOpenAlgorithmProvider(ctypes.byref(self.algorithm),'DES',None,0))
                mode=ctypes.create_unicode_buffer('ChainingModeCBC')
                _checked(_api.BCryptSetProperty(self.algorithm,'ChainingMode',mode,ctypes.sizeof(mode),0))
                length=_U();read=_U()
                _checked(_api.BCryptGetProperty(self.algorithm,'ObjectLength',ctypes.byref(length),ctypes.sizeof(length),ctypes.byref(read),0))
                self.object=ctypes.create_string_buffer(length.value)
                _checked(_api.BCryptGenerateSymmetricKey(self.algorithm,ctypes.byref(self.key),self.object,length.value,key,len(key),0))
            except BaseException:self.close();raise

        def encrypt(self,padded,iv):
            # BCryptEncrypt mutates its IV buffer. Every frame gets a fresh
            # buffer and retains its original IV for the authenticated header.
            state=ctypes.create_string_buffer(iv,8);out=ctypes.create_string_buffer(len(padded));length=_U()
            _checked(_api.BCryptEncrypt(self.key,padded,len(padded),None,state,8,out,len(padded),ctypes.byref(length),0))
            if length.value!=len(padded):raise ProtocolError('Native frame ciphertext length')
            return out.raw

        def close(self):
            try:
                if self.key.value:
                    key=self.key;self.key=_P();_checked(_api.BCryptDestroyKey(key))
            finally:
                if self.algorithm.value:
                    algorithm=self.algorithm;self.algorithm=_P();_checked(_api.BCryptCloseAlgorithmProvider(algorithm,0))


class FrameEncoder:
    def __init__(self,keys):
        self.keys=keys;self.closed=False
        self.cipher=_Cipher(keys.encryption)if sys.platform=='win32'else None

    def encode(self,plaintext,*,spi=0,sequence=1,secure_sequence=None,iv=None):
        if self.closed:raise RuntimeError('Native frame encoder is closed')
        if self.cipher is None:
            return encode_frame(plaintext,self.keys,spi=spi,sequence=sequence,secure_sequence=secure_sequence,iv=iv)
        iv=secrets.token_bytes(8)if iv is None else iv
        if len(iv)!=8:raise ProtocolError('IV must contain 8 bytes')
        n=(7-len(plaintext))%8;padded=plaintext+bytes(range(1,n+1))+bytes([n])
        body=struct.pack('<HI',spi,sequence if secure_sequence is None else secure_sequence)+iv+self.cipher.encrypt(padded,iv)
        body+=hmac.digest(self.keys.mac,body,'md5')[:10]
        return struct.pack('<II',len(body)+8,sequence)+body

    def close(self):
        if self.closed:return
        self.closed=True
        if self.cipher is not None:self.cipher.close()
