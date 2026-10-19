"""Create a pinned TLS certificate locally. Requires cryptography on the build machine."""
import argparse
import datetime
import hashlib
import ipaddress
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def create(directory,host):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    cert_path=directory/'server-cert.pem';key_path=directory/'server-key.pem'
    if cert_path.exists() or key_path.exists():raise ValueError('Refusing to replace existing server identity')
    key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)])
    now=datetime.datetime.now(datetime.timezone.utc)
    try:alternative=x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:alternative=x509.DNSName(host)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5))
          .not_valid_after(now+datetime.timedelta(days=365)).add_extension(x509.SubjectAlternativeName([alternative]),critical=False)
          .sign(key,hashes.SHA256()))
    with key_path.open('xb') as out:out.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    with cert_path.open('xb') as out:out.write(cert.public_bytes(serialization.Encoding.PEM))
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--host',required=True)
    args=parser.parse_args();print(create(args.output_dir,args.host))
