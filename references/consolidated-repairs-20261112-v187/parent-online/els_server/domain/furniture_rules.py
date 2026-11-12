"""Native quest furniture and the literal contents of furniture box136039."""
from functools import lru_cache
import hashlib,json
TEMPLATE=136039
POLICY='current-small-furniture-original-description-20261028-v1'
NPC_POLICY='current-native-npc-furniture-20261108-v1'
# Original HousingItemTemplet.lua SHA6602935c.. plus complete19803A0 bag25.
ROWS=((570011,1,'3e408bd59de5ffcaf917c78f42b011f5cabde54b497f78049565b689f970b7e8'),
      (570012,1,'486579e5048a672101a1e83a977a01dd6c84a666e25e29a97a012fd5b23c7751'),
      (570015,2,'a529b3f1046791cbb2fb4d02d87d1968c4d039fdec07c164b9c7d5225ab000fe'),
      (570016,1,'f4494fc59d92bffa2d63a71750276007dd299083d296255d42c6c03dc43b04d9'))
QUEST_ROWS=((570001,1,'45d7cb71efd809c65074c829fe39b2659d2dd61b64c84ecc4486453133c38937'),
            (570002,1,'1802831e66fa89cefef4697b85e01e4943427b4983b246d53a238a0564f02270'),
            (570014,1,'ac89ab80b5c70ed2fa5f45e89b2c2207aac01faef98918b5edd3b10a5c9aea4d'))
BOX_TEMPLATES=frozenset(t for t,n,h in ROWS)
QUEST_TEMPLATES=frozenset(t for t,n,h in QUEST_ROWS)
SHOP_ROWS=(
 (570003,1,'f9308a8bdc4f76e78882bc36d543be01036e549f2d1aa1f9f4cb24b74cc3bef1'),
 (570004,1,'15506a567117b80ba7201316c9bc30d8c5fd1ac6ec2b31e4f59c683fa7bc7801'),
 (570005,1,'df755bf0d4b1954006170198f67b6007a3cf13ebb0c2c1f7e2372927db625ce1'),
 (570006,1,'1fb1ea5c1ee813851e13e9e0885cf3c1fa32eddc5df2a935c746ce6395fd58a7'),
 (570007,1,'bc222f92dfe61534c8e9f7d325a2ffa59592991502a7df43a06fb05e201351a2'),
 (570008,1,'680bd5a5b3d0c0fe780284ddd57094c9a4655bc88844b892af8a918432c3dd4d'),
 (570009,1,'d612f538fe71b01b8d6133e2b0840f4937a4e8472a569d5b73075b4b5c8bdea3'),
 (570010,1,'26946644b42222e01d68fe16ae6a7b68d2dca0d56edae979409ac82dcb82686a'),
 (570013,1,'b496680acdf59c7f3877724715771ef2ca0f68949754319b82f6739179453d8d'),
)
SHOP_TEMPLATES=frozenset(t for t,n,h in SHOP_ROWS)
NPC_TEMPLATES=BOX_TEMPLATES|SHOP_TEMPLATES
CRAFT_ROWS=(
 (570017, 1, 'f44ddb6a3f5e678d30aa2526f77394aeded29e9fafc9aaf4aae7519b8d127e7a'),
 (570018, 1, '3185a5228b9ef88ef1f33d21556cc07446eb5c03a17d30058844c76a808e8005'),
 (570019, 1, 'e894b971dc0608cd63eab0e67e802a6cd792c7041e899abf43766d825789d8e5'),
 (570020, 1, 'f712bf9fce444a0b7d0a12a9d642c906a59c4cc171c4aefd0681ae4613c0287a'),
 (570021, 1, '2b16bf3f9ff9ef76ef7872b0ad7ebed4806bf9b09bc6c51722a4d894402df95b'),
 (570022, 1, '5cdaa1dfc3735542d67be0dbf49af94512a46f96ff8e15c3ca5d66697e111b17'),
 (570023, 1, '7fad0f0a6c4f339e964aaa8e6fc80e3b5be67011a56a6d83badc1d55aeb883be'),
 (570024, 1, 'a7ea0e4ce3c9f7d9e4ba9767549b1592e7bb8f819590a93c20db8b794578a0b9'),
 (570025, 1, '936bc756b54283826d93b87309c433de5c6293765e8893bd1a63f565821b8761'),
 (570026, 1, 'acccda24b1916aa446292ab58d3b512a9f9f14950e5992ce4dfe27b674c27522'),
 (570027, 1, '6ddb00e9161f1748b1ef9c153be71da5b626b439e7b5ec07047c7f0c667f34a8'),
 (570028, 1, 'baf412ca6e6d4cafbba5622343028667116285899f9fda80db2cfd9ae0f4b8e5'),
 (570029, 1, '71a958be2542002a56c211586f7b3d599eb61772e4342b6d964babc8fe3149c4'),
 (570030, 1, '65fe264b84f2ebae6c6a85612ead1770f82596db3cfdd6f27adf3758c2eae18c'),
 (570031, 1, '5a1a76eb12a06f59c827696dca4c282cbfc8e5a117e90022fcb9feb4d0b8eae8'),
 (570032, 1, '955555a0662dee959afc8cf513dd34b00745a136ebc140fb1a25d962a4f7ea4d'),
 (570033, 1, '9b7e30e5e82f8c3957e1c3934f585d3f9738bb2849eaf98fb0615df6508a4885'),
 (570034, 1, '420148c2cc8edc751fac7bcf8c5ecf3948588c49ce6168815213cc9c30e54de1'),
 (570035, 1, 'adcf4b786d1fcd53e300a11007f512edc7a574654a97ff1460c210088c634afe'),
 (570036, 1, '51a91b81044d2d8ce73e5e94e41c43e0f643d2381c9a209a9cabe6203ad247df'),
 (570037, 1, '9b27b7d701af9663d73021a1717f544a347c79502147f6466cabe036d1022d2a'),
 (570038, 1, '6ba717c6ea55723d688d39b361ddbe56f4d68ef86c74ce37bd0db7ab383ecd79'),
 (570039, 1, '33331a0ff810291a0a90b6af74ed35537354b0c7aaa3208247571160a64acd6e'),
 (570040, 1, 'b7cb9debabedf6d9f42cfd8957d9e1cdf11687ca69eaf661dbd2623c5f861ad3'),
 (570041, 1, 'ee48e926ea1ff0350fc33788049703d8f5971be9d8b7b69b9195f3a76430a33c'),
 (570042, 1, 'b0c77c450474da3a58a79aada5413d8cff3a10652439575753e9435c08686a1e'),
 (570043, 1, '2ea7aee279fcbc69c0f4c889b6b20c16a65dd73012e323a8571982c7b6e2d8c9'),
 (570044, 1, '16cf383acbf070e3274d16b8aef7ad9cac6471e1766954e03f9817644dcc0f97'),
 (570045, 1, '29a448087aff38df906e72f8c67b52e3078ed616bd02ec2edd605c696631126c'),
 (570046, 1, '8b6bc47e7bc4609fd8e7c626b42ed4a9d8b28aa2954cafef9b0f2480e7bf2cc8'),
 (570047, 1, 'fd28a3d00699ca9d4255c918e04c4449ad2ce1cedc9466611e24658b734941cd'),
 (570048, 1, '519a4f74e1a367ab8ffd261cc893adf8d978a461487447cb9ab8d5e39e4900be'),
 (570049, 1, 'fb66c504287a120c03219bd66d1e3072adfa50e81ac3423fc55976a5db910691'),
 (570050, 1, '7991d4f7b72abc9779c54c9092a417e8d7a82adfef4cec17e2ab50aca45b0775'),
 (570051, 1, 'e09810cb43a2109a2aa58be2e6f0f6c1810ebfb58e3539e08e69cd95ce936877'),
 (570052, 1, '4f8906c6dd2e17cc5d1f58924c6fe10e21ca4f6902e5f07ee5923a81f8e80864'),
 (570053, 1, 'a074e3a2f017a3ff4a9566b9c6130d614a18f965287b87745558cf6d6303bceb'),
 (570054, 1, 'e78a4c116949d6267d0d12eaee2861eb79ba2c255725fd0b38500d02b20381ef'),
 (570055, 1, 'b8b2e87f55269fcae6c439a771c9be9dbe0f2b4abd8642631936b9ae821bab19'),
 (570056, 1, '8e179b00bf15839b94bfce69d0ed777c8669916dfe923ffefc03205296fcdae7'),
 (570057, 1, 'efa44c5970da3e8d3e46d42dd4c432f72f211ad22036caed850ef594621a31c3'),
 (570058, 1, '80561cb327fb403e52de1a646467ee57339ce0b1446f55bc135baf07782e0f55'),
 (570059, 1, '655645c17a5b1aa5952c701ffd8c9974268a94970ad673dcec0d112bb74898e3'),
 (570060, 1, '055ebf044273eb8daf915d95c1466bee90b790b52da9c0d08a306504635880d7'),
 (570061, 1, '3fe81770d646a8ec3f06cd1b67f458b3b07921ccd3c92b07d1f068d6d2063de6'),
 (570062, 1, '4cf29c53c37391511bd7653dd0c96a6e0464f86b1256de71421efb73ad3a8775'),
 (570063, 1, '8c2a34d4f77bb4812b5427cab6c7c3878704cc9b9ad97f9cf427a80aba6b7f5d'),
 (570177, 1, '174bb31e226ff1def378ee83a63cc6131984dc8d90be9521b8393535f4676f49'),
 (570178, 1, '2f4576e66bb7b621873d5f83f60bc60e16267cf543f2641a4f569c25a556eb7a'),
 (570179, 1, '04e68a7ad589d85c3ee006ef8927ea6b11ca9e491ae966793af6d099bbf219c1'),
 (570180, 1, '5ff4b460301087099d8513c5f911c23ef2d22e51bce424649b1a3ac7e231d52d'),
 (570181, 1, '089bd5efdfa77ae5c5b3ca3c4466eb76a1f8f3bf0586af7e2d9d9524cef2241e'),
 (570182, 1, '728a89d081f840356cbf9fd8b15d442e9b91ddff366923d45f605aecb6e058e1'),
 (570183, 1, 'e5ae09b5bb2adca94d082cf878890a7165e21cf53945a87e4ed73a659d10750f'),
 (570184, 1, '4bdb226f5f2357fb21f474a9a18c74e75bd41cf4e42492a596eae3461d49436b'),
 (570185, 1, 'c90b62e10db28adbce0a074416254aa3075606c4170ea9670c84c35f16226cdd'),
 (570186, 1, '5a734ab80af1dcdd11884463ef81a64c61034547006f504d09bc9a921d70a091'),
 (570187, 1, '3f21b8f52b59cc68b916e82985a1fb82c3670a7bd6989fd0c152774369c5aa86'),
 (570188, 1, '4c737f3ceb030ac8f00925c8f2d08d352fdd14c43aa4ba425b4e01797d28fbaa'),
 (570189, 1, '2c1bb1514d3467d8dc4e7236229a97279a2d8a6350f25781a16ed34d7f5a9ee0'),
 (570190, 1, 'c0cbe71400863c0dd961711a803ec7a48ce9e543bc87d0a31fb1b8b98b332773'),
 (570191, 1, '1c6b769f869386e72b406fdf76ce808912848041dd2afeb7556a1e712fb164ad'),
 (570192, 1, 'ae197b1e96a0e4f2eb678d2260e94f139f83d879f742421741bdd3a9d5e264e9'),
 (570193, 1, '4fe8d71ed8d5727cd2296406abe39b1741631c1ec1958cd7f4ce7a8c94eda061'),
 (570194, 1, '0c1ef7a07429bf900b7e02a681510b6dd4f4d92b43e4a70600f04c6b94f20a47'),
 (570195, 1, '0c971d68f2a61da64f4ec22b2f9e93d204bead899e8f779218cf7c6b325bc4a2'),
 (570196, 1, 'abfdf777d23650f9be9204623aec41eae19a7a5e24e1e435af046c699f7ee1fd'),
 (570197, 1, '2fa478e75ccf3f6d2f8a0785fa078be0267868181a1bb404bb316db39445df24'),
 (570198, 1, 'f69ade5d114b93649f08c46939d83825031cb604752887dcb42a7429ceedc82c'),
 (570199, 1, 'bc935ba1c26b20e642055b4975786a0afa8d8f4b0b14539342fbbb6e82d04572'),
 (570200, 1, 'd7e3832c7dc6b35e6e08f9c43604d4468071b6fb7c330458225c8731cbbef3c9'),
 (570201, 1, 'aaf5bc1e05d43a24057fdeffa00460fc7b12dfce3593e023c90fa0e97c90fe01'),
 (570202, 1, '3ef9dab5a50f1aa7fdedd9bd7415af52191c2bc8b2f4c6b617cebd05dacc6645'),
 (570203, 1, '1b615df969eb829a7cbe1dee53b669a59bcda9be07ccd7070e9d6708c77d4e67'),
 (570204, 1, '171da8fc6542eb5452f7da99231c869c20ee211815f816ae3ce0b9175fb05640'),
 (570206, 1, '5ee5ec0eb6fecd25a7ca7168819a930a8e4b5ffea8695601738a7466bff8c92b'),
 (570207, 1, 'cd862b2720f7d2f112065e1852e6395acb320c8fdd70984f05bbb9dfd1c7b3ff'),
 (570209, 1, 'c8f18b06d67e77698554799fcf1466d490aa41821645a6cb7a9d74ee7de9475d'),
 (570210, 1, '80214115d188ae11ad16c4de1e7fdfe90dbe615719471bb5e25a278638071273'),
 (570211, 1, '5a3039cc1e514ea2ed4f29e6df2b9c732bc0d622b898a4e6c74cd0f7d3a232df'),
 (570212, 1, '672744db81efe3bf056df9b03d3b50d4eaff6f59247334392b2636d4944831b3'),
 (570213, 1, 'f399ae2c504133653cb1af34e52a988f9fa4531dc86fd3377d24800aa2f641b6'),
 (570214, 1, 'b4f81775a61a8cb54796d82d9b9dbdc5b88b4a6bd04a917894467b2ab4c3feed'),
 (570217, 1, '0dca0220b168ab0a1b32a756b8af48ad3d40f26ebf6e8a4629dd6fc58bae91b7'),
 (570218, 1, '5b0d65fe0f9ec0656bbe4843e24200261272b51b6ead9abd2e6acf1e8d4f8b5b'),
 (570223, 1, '88b6090ac42f7836d2d263d17e5a6c4191efe93800877367ec94fa275dc3a097'),
 (570226, 1, 'fe1268ec561025aefe21cf3953540dcfae87f8cc62f0deca3dafdb323f5c9dca'),
 (570227, 1, '9f11e8b3fe668a6f0ade6d1d14836b0316912cce1ef0d9c5390f133348a31222'),
 (570228, 1, 'aaf14e88a23d96d44a8c998f56ab40223697213ee79895e170f240109aa00ad9'),
 (570574, 1, '0238d5821340f2e88daa6422eab09d36482bd8060df343a2b037ccf48d35da36'),
 (570575, 1, 'e04b21be7da97dd723973629b5fbc0242be76d4255760c85c4cc7670f028c560'),
 (570576, 1, '19a1143b5c647f6c442812f721c3212bf51cdb0b99217f8999447eb1c2d7fd5a'),
 (570577, 1, '3f05ec417a6eb8fb378c99ac23c0fcedfd4a93f8dca1fa21311ce725f9915d3d'),
 (570578, 1, '4bcb065a482805bbc8348445480e41eebf3cc75307bb5d79a06ce463c05516f1'),
 (570579, 1, 'c9e7920160f6fca8cdd4974b4fc56f6f22a4cfe3b5c3781c867f4fe9a9f7f02f'),
 (570580, 1, '12ccdca122b7cdd4e078a899ccf2a5f1d04cd3d4042fd842fd2ed62de207d70e'),
 (570581, 1, '76d9a3582ca167f58e1119b43c9dd99390df0e42b75930ad65f4687fbb8de341'),
 (570582, 1, '2d162c44866b4358ff23590d873f4d4fb746260606b21122c189bd315d9672f4'),
 (570583, 1, '7e3bfdbe26b7d39d2f89bf6e8108d54139839f605022cc9a012c4ecb5069b899'),
 (570584, 1, '3fc8370028e907a5b8f606d2bbae91e9c9d4a653e97ce0da2529da68ac81faf9'),
 (570585, 1, '4d3766086474397c0116aa2c7e09ecd4581a075ac4aa5522536a0879fbe02eaf'),
 (570586, 1, '0fba81f1b030491e38198246c67a0060e27cd9dd0eae67499dbacb0579e4af8f'),
 (570587, 1, 'a7853b3e0ae72d4ea86d45519a8a04f9b1ef2ca663915a291cad92bd52e70b54'),
 (570588, 1, '835902b78faf78eb2eea749ee214ea8091c80e68b4371450e51317678d578b92'),
 (570589, 1, '595b9c1413a94684a34494097ed4fbe28fdb439367fbb2a5c85d477e80ef3479'),
 (570590, 1, '04030f203562004e691f1c1e9b43ab751725d2a16ad6abb8da584e5eb409cea1'),
 (570591, 1, '2744242025344b6062369978264e54374f967dad33804cfe4d1c5d5c79d7b718'),
 (570592, 1, '71cae394ea1c37e4c658f80edcacee555c57b73e97c0fbbc22e6a3ee794a89db'),
 (570593, 1, 'ab7f5d84ca6857b1317a484933fe75134bfb839b1833dc5ab4599ffd1d1e7d21'),
 (570594, 1, 'd05148450a07ab767c95dba39d305edd9a5632d6c2f3dd27cfee11b4bd819433'),
 (570595, 1, 'e10b61ce45bbccea646a1fce3f36eed112afceb9f46d6279c41aa1814d1aa8ca'),
 (570596, 1, '1cd95256a4f7ad351041dfbce7661623d558d68393084441e32309e77ed55969'),
 (570597, 1, 'cdd0939db23c38a6b4255f7aa7314d8d760cc1b894324c4be57374a3f834feb9'),
 (570598, 1, 'd7825c8a6c7dbda6180ea30d4d91996040d9d3542906f369eda2ffa20624ac61'),
 (570599, 1, 'f1732dedb76a02b0ed3999884a2c1968943e7333dc1bab87c847d02600588929'),
 (570600, 1, '4da4a325357ba93589c334fb59454725d2cfd5327a84c49e31e6dc79e0bc08be'),
 (570601, 1, '9ea44e945ba8712ef8c623db38b58ff3e02921c18fd3552f5cf22b0ea8f4a827'),
 (570602, 1, 'e5b2420a37fc40dd3d423f93cd06588cfabd12cc516e3d7e69a47f858ff7abe5'),
 (570603, 1, 'b1b5975262fac136d7ebf57bd16200d8ec2daecb857a2b8f6d0ef5619f6635ff'),
 (570604, 1, 'ce58267a5a63cb51bce49aa1de522c87dbb5a24c1f650de6ca9f62fc4a82780e'),
 (570605, 1, '89d47b771f003cf1fcd50f8efde28814b4bf9f2b7063181cdc588d3a3a3d2c8a'),
 (570606, 1, 'bb5c9f45415278cb6447ac0ad511aaab58975b5ff820bfcafa3b8d4b76443ddd'),
 (570607, 1, 'ca9ceef2962a02a5ed56050c8d19feb21f8d9dfb2872d8e0b92353a898f6301c'),
 (570608, 1, '60d887abd7d00597185dfcb15fae79c8914f7790fb5e88293b926031c7a0592b'),
 (570609, 1, 'c8f35684de39d42d09e02fdd65ba3c0a01219817fe218ad922f930339009329d'),
 (570610, 1, '02dccdbdee2241618b19be6b186d04a71318591e80b1ff10b0560875340e78d8'),
 (570611, 1, '922409f0e4565113b02315d8c64cb77efaf5013e28a3d955f69f43b24973e462'),
 (570612, 1, 'e3387847ae2b3ecdee9f1aa6b586cf5160ef1ec85fd71f4367e0c0be572625c1'),
 (570613, 1, '7ea66539a0bb073a754054db7e039db0b4dc491da76679eb931c7f4059bcb61d'),
 (570614, 1, '51c90b09ba4c01a85b96fde6dd750ce6ea017fb35d09a23f77d2677fc4121db8'),
 (570615, 1, 'da820997662925b50c78d2bdbd7bfda803b1c30edd88f73234faf5ca023a99b5'),
 (570616, 1, '8a204b8bc23e1d2e74f247730bcfafbd54f7ec6176e27d7c5e9b9241e9f3b1d1'),
 (570617, 1, 'a1721761b8bcc42bdedc978d5a47319848936f8b21a67093fb23c68a7806f8a6'),
 (570618, 1, '0a79adc35005dbca683ddf5748c02c85a2a8ba495e7c3003fc7b5effc63f86ef'),
 (570619, 1, '3c9750e0cce9a118ca89a7ddff7e8cab9f4a5350ad95cd3f4d5b3071a353fc33'),
 (570620, 1, 'ff0e12e143782bfc52d7ed0044b91a260c7351758c2596b8fcac6c7dc8a51187'),
 (570621, 1, 'e044bb745b052d8025079e9d152cda3c9b4ad220c0816ecfb8e22f20487d1a3f'),
 (570622, 1, 'f90da0c077eacf7acf3a753fc03a670b5c00ab1caf0756177f32151d0d4157e3'),
 (570623, 1, '1b998111d1824d349065bd8d67ff4fe09799c8a1145f450fc6eb58e2209c8119'),
 (570624, 1, '1192656e92a190a024c96bc0168f9ce8c53fee3343a1498ea8211cdb7a993396'),
 (570625, 1, '426e198546aace6852d353273d5cd102d2b0414d4c16b65acfa9d843f17252b7'),
 (570626, 1, 'ac1a4a99307f78629b15df0685f30f39245f3d04e52767ab18131fb18e416536'),
 (570627, 1, '019dd30b4a68cfa2ba30c6af4848940e97f4ae3a94ebcff8d3a1513a9ac04c46'),
 (570628, 1, 'bc8370cd4737890459e4976360959e9be42d0c0ad9e49d7f8f9beccddd0df9fc'),
 (570629, 1, '761e694fbaae355d7d1a6eafb1198a206a387fd21ff4fa8a42d0a60e27f81754'),
 (570630, 1, '5ba77244ea82cd8cc7e0fc8ddff74657836b31588760b4d037020f2ac7d69615'),
 (570631, 1, '6342d76f868b2f1c30e36296a8ea1e97d5d1453de21e225e5a880324832bfe41'),
 (570632, 1, 'c8cbb03de6ad794221c5befa25286f26e75f918a0ee871dbd24a0e08b0556187'),
 (570633, 1, '79530e5c778dfbe3876151ee53e95439b181b3c10a59d8b1a3fe27dd9eeae280'),
 (570634, 1, 'a8da67f886f90587a74606ba2387680e656fd6f0eea7b8121832f7993d6cdbe6'),
 (711684, 1, '22cf09f0dd8ea1dbbde2ab200055dfe10bcdaa26192d7028724f584895bc4882'),
 (711685, 1, 'de42c9ad3cc7ae48a212477697e0268d1f1c304740bf56cc0ab0eed03f106c59'),
 (711686, 1, '6879b6cac052b1019860dc05d69f1658b36da8a7e6625ec3b3fdc5cb96bd1dd9'),
 (711687, 1, 'cdab8a54e0d9c9846fdea19816e02d32c298c69498025b3e0ce18a28e8d2c36e'),
 (711688, 1, '54315f981c59b3b9d67070a469243e596e9f6bd58fd12f63e86bf3ff30553a3c'),
 (711689, 1, 'f004b041c7a16a236a0f725ac22b1efd6acbed280c4d581a8f03d66adff38d41'),
 (711690, 1, '828e4eaf728e3beef4ab7c4a97d0aef90543d369f6515cd8cb8eb699274b5055'),
 (711691, 1, '4528cb1b35f4d99569909ace13b3c530165adfcb98937091a58197e2c904eac9'),
 (711692, 1, '12f5ba0334fb701c86a92227f8ebab6baf12de8b134fdc072bffaae353077099'),
 (711693, 1, 'ddeec41d2a8cd15fbf5f8a3cccedcde0339bdb564cc77ff6e201f888751dcda3'),
 (711694, 1, '9695e8e6ae572304fd736ab2c2d03bec8a2b2621cffd7202c313dd65b81bac6c'),
 (711695, 1, 'cb15bc8e44b98ed523cf0575a1aa3e7cbbcfd0eabeadb8b053ce58b0512d48f6'),
 (711696, 1, '12a5e1f57d75be95976f399b9e0513613b3cf643846d12ce3fc54dbb57ffa742'),
 (713286, 1, '46b81922c058c9bec77d41e77565fbe983be921f5534c0cdb2b30a176c5891c8'),
)
CRAFT_TEMPLATES=frozenset(t for t,n,h in CRAFT_ROWS)
from els_server.domain.housing_pet_rules import ROWS as PET_ROWS,TEMPLATES as PET_TEMPLATES,mat
TEMPLATES=NPC_TEMPLATES|QUEST_TEMPLATES|PET_TEMPLATES|CRAFT_TEMPLATES
# Original usable location1 maps to floor1; wall2 maps to left/right2/3.
# Native skin surfaces retain their separate position4/5/6 distinction.
POSITION_TYPES={570001:(1,),570002:(1,),570014:(1,),570011:(2,3),570012:(2,3),570015:(5,6),570016:(4,)}

POSITION_TYPES.update({t:(1,)for t in PET_TEMPLATES|SHOP_TEMPLATES})
POSITION_TYPES.update({
 570017:(1,),
 570018:(1,),
 570019:(1,),
 570020:(1,),
 570021:(1,),
 570022:(1,),
 570023:(1,),
 570024:(1,),
 570025:(1,),
 570026:(2, 3),
 570027:(2, 3),
 570028:(2, 3),
 570029:(1,),
 570030:(1,),
 570031:(2, 3),
 570032:(2, 3),
 570033:(5, 6),
 570034:(4,),
 570035:(1,),
 570036:(1,),
 570037:(1,),
 570038:(1,),
 570039:(1,),
 570040:(1,),
 570041:(1,),
 570042:(2, 3),
 570043:(2, 3),
 570044:(5, 6),
 570045:(4,),
 570046:(1,),
 570047:(1,),
 570048:(1,),
 570049:(1,),
 570050:(1,),
 570051:(1,),
 570052:(1,),
 570053:(2, 3),
 570054:(2, 3),
 570055:(5, 6),
 570056:(4,),
 570057:(5, 6),
 570058:(4,),
 570059:(5, 6),
 570060:(4,),
 570061:(5, 6),
 570062:(5, 6),
 570063:(5, 6),
 570177:(1,),
 570178:(1,),
 570179:(1,),
 570180:(1,),
 570181:(1,),
 570182:(1,),
 570183:(1,),
 570184:(1,),
 570185:(1,),
 570186:(1,),
 570187:(1,),
 570188:(1,),
 570189:(2, 3),
 570190:(2, 3),
 570191:(2, 3),
 570192:(5, 6),
 570193:(4,),
 570194:(1,),
 570195:(1,),
 570196:(1,),
 570197:(1,),
 570198:(1,),
 570199:(1,),
 570200:(1,),
 570201:(1,),
 570202:(1,),
 570203:(1,),
 570204:(1,),
 570206:(2, 3),
 570207:(2, 3),
 570209:(5, 6),
 570210:(4,),
 570211:(1,),
 570212:(1,),
 570213:(1,),
 570214:(1,),
 570217:(1,),
 570218:(1,),
 570223:(2, 3),
 570226:(5, 6),
 570227:(4,),
 570228:(5, 6),
 570574:(2, 3),
 570575:(2, 3),
 570576:(2, 3),
 570577:(2, 3),
 570578:(2, 3),
 570579:(2, 3),
 570580:(2, 3),
 570581:(2, 3),
 570582:(2, 3),
 570583:(2, 3),
 570584:(2, 3),
 570585:(2, 3),
 570586:(2, 3),
 570587:(2, 3),
 570588:(2, 3),
 570589:(2, 3),
 570590:(2, 3),
 570591:(2, 3),
 570592:(2, 3),
 570593:(2, 3),
 570594:(2, 3),
 570595:(2, 3),
 570596:(2, 3),
 570597:(2, 3),
 570598:(2, 3),
 570599:(2, 3),
 570600:(2, 3),
 570601:(2, 3),
 570602:(2, 3),
 570603:(2, 3),
 570604:(2, 3),
 570605:(2, 3),
 570606:(2, 3),
 570607:(2, 3),
 570608:(2, 3),
 570609:(2, 3),
 570610:(2, 3),
 570611:(2, 3),
 570612:(2, 3),
 570613:(2, 3),
 570614:(2, 3),
 570615:(2, 3),
 570616:(2, 3),
 570617:(2, 3),
 570618:(2, 3),
 570619:(2, 3),
 570620:(2, 3),
 570621:(2, 3),
 570622:(2, 3),
 570623:(2, 3),
 570624:(2, 3),
 570625:(2, 3),
 570626:(2, 3),
 570627:(2, 3),
 570628:(2, 3),
 570629:(2, 3),
 570630:(2, 3),
 570631:(2, 3),
 570632:(2, 3),
 570633:(2, 3),
 570634:(2, 3),
 711684:(2, 3),
 711685:(2, 3),
 711686:(2, 3),
 711687:(2, 3),
 711688:(2, 3),
 711689:(2, 3),
 711690:(2, 3),
 711691:(2, 3),
 711692:(2, 3),
 711693:(2, 3),
 711694:(2, 3),
 711695:(2, 3),
 711696:(2, 3),
 713286:(2, 3),
})
LEGACY_FLOOR_POSITION_TEMPLATES=QUEST_TEMPLATES|PET_TEMPLATES

@lru_cache(maxsize=1)
def definitions():
 from els_server.game_data import client_data,CLIENT_SHA
 c=client_data()
 if CLIENT_SHA!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709':raise ValueError('Furniture native build')
 if hashlib.sha256(c.item(TEMPLATE)['record']).hexdigest()!='0567ac6833f56ac2722e347d7b0cd8b2d5d5ed6df70b3f71baaf0c53ea273398':raise ValueError('Furniture box original definition')
 for t,n,h in ROWS+QUEST_ROWS+PET_ROWS+SHOP_ROWS+CRAFT_ROWS:
  item=c.item(t)
  if(item['metadata'],item['item_type'])!=(0,16)or hashlib.sha256(item['record']).hexdigest()!=h:raise ValueError('Furniture original child definition')
 return tuple(dict(template=t,quantity=n,metadata=0,group=25)for t,n,h in ROWS+QUEST_ROWS+PET_ROWS+SHOP_ROWS+CRAFT_ROWS)

def plan():return[dict(r)for r in definitions()if r['template']in BOX_TEMPLATES]

def authorize_output(template,source):
 if template not in NPC_TEMPLATES|CRAFT_TEMPLATES or source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);identity=json.loads(source._source)
 if source.kind=='manufacture':
  from els_server.manufacture_data import manufacture_data
  recipe=manufacture_data().recipe(identity['recipe'])
  if (template not in CRAFT_TEMPLATES or recipe['definition']['m_ManufactureType']!=9
      or recipe['result_registrations']!=[template]
      or identity.get('policy')!='ariel-native-furniture-manufacture-v1'
      or identity.get('owner')!=source.owner or identity.get('operation')!=source.operation):
   raise ValueError('Furniture exact native manufacture source')
  source.validate_template(template)
  return True
 if source.kind=='npc_trade':
  from els_server.domain.npc_trade import stock
  town,merchant=identity.get('town'),identity.get('merchant')
  if template in SHOP_TEMPLATES and (town not in range(20000,20014) or merchant!=10018):
   raise ValueError('Basic furniture requires Ariel in an ordinary village')
  if(identity.get('policy')!=NPC_POLICY or identity.get('owner')!=source.owner
     or identity.get('operation')!=source.operation
     or template not in stock().get((town,merchant),())):raise ValueError('Furniture exact native merchant source')
  source.validate_template(template)
  return True
 if(template not in BOX_TEMPLATES or source.kind!='box'or identity.get('policy')!=POLICY or identity.get('template')!=TEMPLATE
    or identity.get('owner')!=source.owner or type(identity.get('uid'))is not int or identity['uid']<=0):raise ValueError('Furniture exact owned-box source')
 source.validate_plan(plan());return True

def validate_layout(layout,items,*,mutating=False,now=None,legacy_floor_locations=False):
 from els_server.protocol.housing_layout_messages import LAYOUT,encode
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 encode(LAYOUT,layout)
 legacy,new,grid,reserved,floor=layout
 if reserved!=0 or not 0<=floor<=2:raise ValueError('Furniture native floor fields')
 owned={i['uid']:i for i in items if i['template']in TEMPLATES and i['metadata']==0 and i['group']==25 and i['count']==1}
 used=set();skins=set()
 for modern,rows in((False,legacy),(True,new)):
  for key,value in rows:
   if modern:uid,t,position,xyz,direction=value;level=0
   else:
    position,uid,t,x,y,item_floor=value;xyz=(x,y,0);level=0
    if item_floor!=floor:raise ValueError('Furniture record floor differs from layout')
   if key!=uid or uid in used or uid not in owned or owned[uid]['template']!=t:raise ValueError('Furniture unique owned UID/template')
   # Original244D4A0 applies grid furniture through2451350 and binds
   # Game+B00 to its pet mat.244D960 free-position records create a model
   # without this binding, so accepting a pet mat there cannot spawn pets.
   if modern and t in PET_TEMPLATES:raise ValueError('Housing pet mats require native grid placement')
   item=owned[uid];require_current(item,now=now)
   if mutating:require_unlocked(item,now=now)
   legacy_position=legacy_floor_locations and not mutating and floor==0 and t in LEGACY_FLOOR_POSITION_TEMPLATES and position in(2,3)
   if item.get('sealed',False)or(position not in POSITION_TYPES[t]and not legacy_position)or level!=0:raise ValueError('Furniture native placement kind')
   #Same bounded finite coordinates as current native housing readiness.
   #Client-native geometry/collision keeps its original coordinate convention.
   if any(abs(v)>1000000 for v in xyz):raise ValueError('Furniture position bounds')
   if position in(4,5,6):
    if position in skins:raise ValueError('Duplicate furniture surface skin')
    skins.add(position)
   used.add(uid)
 mat(layout)
 from els_server.domain.bag_capacity import FURNITURE_CAPACITY
 if len(used)>FURNITURE_CAPACITY:raise ValueError('Furniture bag allowance')
 cells=0
 for kind,rows in grid:
  if not 0<=kind<=7 or len(rows)>128 or any(len(row)>128 for row in rows):raise ValueError('Furniture grid bounds')
  for row in rows:
   cells+=len(row)
   if cells>8192 or any(v not in used and v not in(0,2**64-1)for v in row):raise ValueError('Furniture foreign grid reference')
 return layout
