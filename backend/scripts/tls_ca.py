"""
CA propia de la instalación y certificados de servidor por sucursal (HTTPS/WSS).

La clave de la CA NUNCA debe ir al repositorio ni al PC de la sucursal: se guarda en el
equipo del instalador (por defecto ~/.santander-ca). El certificado público de la CA
(santander_ca.crt) es el que se embebe en el APK.

Uso:
  python scripts/tls_ca.py init-ca
  python scripts/tls_ca.py issue --ip 192.168.1.155 --ip 10.147.17.5 [--dns panel.local]
      genera server.crt / server.key en backend/data/tls/ (o --out DIR)
  python scripts/tls_ca.py show data/tls/server.crt
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CA_DIR = Path.home() / ".santander-ca"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "tls"
CA_NAME = "Santander Control Accesos CA"


def _write_private_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_ca(ca_dir: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    crt = ca_dir / "santander_ca.crt"
    key = ca_dir / "santander_ca.key"
    if not crt.exists() or not key.exists():
        sys.exit(f"No hay CA en {ca_dir}. Ejecuta primero: init-ca")
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    pkey = serialization.load_pem_private_key(key.read_bytes(), password=None)
    assert isinstance(pkey, ec.EllipticCurvePrivateKey)
    return cert, pkey


def cmd_init_ca(args: argparse.Namespace) -> None:
    ca_dir = Path(args.ca_dir)
    ca_dir.mkdir(parents=True, exist_ok=True)
    crt_path = ca_dir / "santander_ca.crt"
    if crt_path.exists() and not args.force:
        sys.exit(f"Ya existe {crt_path}. Usa --force solo si quieres invalidar todos los APK actuales.")
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAIMA Seguridad"),
            x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME),
        ]
    )
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365 * 20))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private_key(ca_dir / "santander_ca.key", key)
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"CA creada en {ca_dir}")
    print(f"  Certificado público (va en el APK): {crt_path}")
    print(f"  Clave privada (guardar a salvo, NO en el repo): {ca_dir / 'santander_ca.key'}")


def cmd_issue(args: argparse.Namespace) -> None:
    ca_cert, ca_key = _load_ca(Path(args.ca_dir))
    ips = [ipaddress.ip_address(i) for i in (args.ip or [])]
    dns = list(args.dns or [])
    if not ips and not dns:
        sys.exit("Indica al menos una --ip (IP con la que las tablets llegan al panel)")
    if "localhost" not in dns:
        dns.append("localhost")
    if ipaddress.ip_address("127.0.0.1") not in ips:
        ips.append(ipaddress.ip_address("127.0.0.1"))

    key = ec.generate_private_key(ec.SECP256R1())
    cn = args.name or (str(ips[0]) if ips else dns[0])
    now = dt.datetime.now(dt.timezone.utc)
    san = [x509.IPAddress(i) for i in ips] + [x509.DNSName(d) for d in dns]
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAIMA Seguridad"),
                    x509.NameAttribute(NameOID.COMMON_NAME, cn),
                ]
            )
        )
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=int(args.days)))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                key_agreement=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _write_private_key(out / "server.key", key)
    # Cadena completa: servidor + CA (algunos clientes la necesitan para validar)
    (out / "server.crt").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM)
    )
    print(f"Certificado de servidor emitido en {out}")
    print(f"  SAN: {', '.join(str(i) for i in ips + dns)}")
    print(f"  Válido hasta: {cert.not_valid_after_utc:%Y-%m-%d}")
    print("  En backend/.env:  TLS_CERT_FILE=./data/tls/server.crt  TLS_KEY_FILE=./data/tls/server.key")


def cmd_show(args: argparse.Namespace) -> None:
    cert = x509.load_pem_x509_certificate(Path(args.cert).read_bytes())
    print("Sujeto:", cert.subject.rfc4514_string())
    print("Emisor:", cert.issuer.rfc4514_string())
    print("Válido:", cert.not_valid_before_utc, "-", cert.not_valid_after_utc)
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        print("SAN:", ", ".join(str(v.value) for v in san))
    except x509.ExtensionNotFound:
        pass


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ca-dir", default=str(DEFAULT_CA_DIR))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-ca", help="Crear la CA de la instalación (una sola vez)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init_ca)

    s = sub.add_parser("issue", help="Emitir certificado de servidor para una sucursal")
    s.add_argument("--ip", action="append", help="IP del panel (repetible: LAN, ZeroTier…)")
    s.add_argument("--dns", action="append", help="Nombre DNS opcional (repetible)")
    s.add_argument("--name", help="CN del certificado (por defecto la primera IP)")
    s.add_argument("--days", default=825, help="Validez en días (por defecto 825)")
    s.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    s.set_defaults(func=cmd_issue)

    s = sub.add_parser("show", help="Mostrar datos de un certificado")
    s.add_argument("cert")
    s.set_defaults(func=cmd_show)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
