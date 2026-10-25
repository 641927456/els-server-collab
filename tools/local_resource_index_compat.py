"""Pin the local resource archives before selecting their native disk index.

在固定客户端里，有 36 个资源包的「内嵌目录记录」与「磁盘目录头」不一致：
客户端优先采用内嵌那份，导致内层资源加载失败、界面整屏灰掉。
本模块把这 36 个包的描述符强制改写回磁盘头（adler / time_sum / size / count），
让原生加载器自己去解析磁盘索引，从而恢复渲染。

由诊断运行 20261024-111559 的 407 个资源包观测结果生成：
407 个包中恰好 36 个 descriptor != disk，live_count 全部与磁盘一致。
与 docs/AUXILIARY_NATIVE_ACCEPTANCE_20261021.md 记录的「36 次目录选择」吻合。

This is a local mixed-resource profile, not evidence of retail-version parity.
The native archive reader still checks and parses the on-disk index. A private
expected-header copy prevents the newer embedded index from replacing it.
"""
import hashlib,json,os,struct,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

PINNED={
    'data002.kom':  '80d41ade3fc24ca9b2551f41ce878b797a9fbd64177732dba44623ad02705906',
    'data015.kom':  'e1d47d54fb4e0190a2ea3db53687d6f6387ca90b7c73d85465184e2caa98b315',
    'data016.kom':  '7926dd87a8fd38453ab789d3af484fb6a691df6e0e9ff5deaa3b264b85d0d7b5',
    'data017.kom':  '00438999938dbf2005cbb970a9456311aef7e40ac83d8627ade61317f17f11b6',
    'data018.kom':  '76690f3d56f882b58ac0c5ed47e8efa953753b23a1e1fc54812649cb7ab655fd',
    'data019.kom':  'c8c52d970c9954b0ea573bb5d59c39053dcaae943e1d5ff6ec73fc0b91d12e53',
    'data020.kom':  '82a4f42a1ec4b56246f87fb5177963a17ae669e3b4493a1bf1e92f6c13e573f4',
    'data035.kom':  '5adc3150a1c8dcb35e3015d2e0e208320ec926e6008ff445ebb9f9fa4692a241',
    'data036.kom':  '56bb739e04e856e2ebf4c93c0df0cca7c181914e65d7cf4d140e167f593c6601',
    'data037.kom':  'a972add6eed7efd6af448cf05ff5a2cd4db9da70f19be5e8032269269be3a308',
    'data040.kom':  '99732fcc0df12a6d10bcce11dfa36ccca100ef70dde775a3711db17a68687106',
    'data044.kom':  '6fe94c231469154a4790f113a1eb703b3e5166fed6377b8f2f0d7f92e7a7305e',
    'data107.kom':  '90443f4226112c5469035e0256396cd07eb72f11caf59f54a526c89696c6677f',
    'data130.kom':  '2a3568fa93638d0306d6af2b6cc62fa7e3df2da8c371361838c18b59b1e57ebd',
    'data131.kom':  '9313b0bffd8ba095c03e3f48bf64abbdfd2f0ca76c7f3c820a11d4327535ce90',
    'data143.kom':  '16204423d385148b6b945ef987fe5f99c0b10844eb26a77574885e017bdb4288',
    'data148.kom':  '8752e6e22276d7a308e9d87cb45a80b1e3f47896758cf6c9c16e6c16fe93a913',
    'data158.kom':  'b5d58f150fed1f126aa9dcc087378a9f66350ccc9f4b129c949300cbd5c2bc68',
    'data159.kom':  '5e7ecafa3550b8768452d94a3ac7e54bcc392c624c9b66af10f8f5646017db88',
    'data185.kom':  '1223340c67ef870ab662e74e3f2e8742c7ae3db032a9c63d16a222f6d931077d',
    'data211.kom':  'fa6e3243c81d2a99d6b88a435065ab4c02734625bf819efdb7c920bb80fac566',
    'data216.kom':  'f8a443d3ab9701002d61e99be45eb98df38a4312e515d3355956ad36b989ad08',
    'data230.kom':  'dc6ec8517af3be338c6041f07dd68b1455ae6f91f2303a37569e74fe34f3caf8',
    'data248.kom':  'efd358dc3d486b3bcd9225f84e84749de348bc6679d50b8f7d0c951fa283b9e3',
    'data255.kom':  '7223accc0eb3bec399d7e3554b0f878e22415d317fdf84681cf510beb720aa97',
    'data271.kom':  '051759bb168c8007d43230c6da9af8747c42cd0c5aee027132ed4107d7b9fe7a',
    'data275.kom':  'bd87d2322d2e6e23716a2670f683a7cd3bd7a015c7185a7f012b5c4fa2f83e3d',
    'data323.kom':  'f1f2438c7eb76493b1433f10116dd3eca3273a96c277b0fa3de0e2b5e9199352',
    'data327.kom':  '30dca258540f44a2d6e28f15e1ed40ede92a7995d002048c0a3bc5a62611445c',
    'data331.kom':  '108184055bd55ab6e20cf11aa3a95e4ecba8716880764cd59f6d767d520e62f8',
    'data370.kom':  'aac7047248d50a4a01d61e49a0ea90de78b5efd63c9da9730694f2de7f4c151b',
    'datai005.kom': '1914fd471f991b12ff5691739079107482aa55c54750cbd8f08317c2ef2da461',
    'datai008.kom': '046fd07cbbca5caeeb197de0565dd80f2608d7dfab5bb3a6ad828996deb06475',
    'datai015.kom': '739f89d75e6fe5408f8d0b4d61aabfacb73d726c089e524b70a77365f3f275ac',
    'datai025.kom': '341fd57efee463c027678708c4125aa249adbcffc195ce52b3bf22050903da71',
    'datai031.kom': 'cf06d1dae8afe492c7f2ccf5d9afe11eec236c0c1236b69f7c91424c52d7062a'
}

def _spec(path,digest):
    """流式校验文件，只读头部与目录块，不把整个档案读进内存。"""
    with path.open('rb') as handle:
        if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:
            return None
        handle.seek(0)
        header=handle.read(72)
        if len(header)!=72:raise ValueError('Invalid disk directory: '+path.name)
        count,_,time_sum,adler,size=struct.unpack_from('<5I',header,52)
        if size>path.stat().st_size-72:raise ValueError('Invalid disk directory: '+path.name)
        raw=handle.read(size)
    if zlib.adler32(raw)!=adler:raise ValueError('Invalid disk directory: '+path.name)
    return {'sha256':digest,'header':header.hex(),'count':count,'adler':adler,'time_sum':time_sum,'size':size}

def source(image,directory,allow_variants=False):
    if hashlib.sha256(image).hexdigest()!='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a':
        raise ValueError('Unverified resource-index client')
    if os.environ.get('ELS_INDEX_OBSERVE'):
        # 诊断模式：只记录磁盘头与内嵌目录描述符的差异，不写任何客户端内存。
        return (ROOT/'tools/local_resource_index_probe.js').read_text(encoding='utf8').replace(
            '__INDEX_PREFIX__',image[0x3653b0:0x3653c0].hex())
    specs={}
    for name,digest in PINNED.items():
        path=Path(directory)/name
        if not path.is_file():
            if not allow_variants:raise ValueError('Unverified local archive: '+name)
            print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='original',reason='archive-not-witnessed')),flush=True)
            continue
        spec=_spec(path,digest)
        if spec is None:
            if not allow_variants:raise ValueError('Unverified local archive: '+name)
            print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='original',reason='archive-not-witnessed')),flush=True)
            continue
        specs[name]=spec
        if allow_variants:print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='witnessed-disk-index',sha256=digest)),flush=True)
    if not specs:return None
    return (ROOT/'tools/local_resource_index_compat.js').read_text(encoding='utf8').replace('__INDEX_SPECS__',json.dumps(specs)).replace('__INDEX_PREFIX__',image[0x3653b0:0x3653c0].hex())
