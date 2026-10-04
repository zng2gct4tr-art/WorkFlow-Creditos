"""Private object storage and fail-closed upload inspection."""

import hashlib
import base64
import os
from pathlib import Path
import socket
import struct
import zipfile
import tempfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

MIMES = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    "doc": {"application/msword", "application/x-ole-storage", "application/CDFV2"},
    "xls": {
        "application/vnd.ms-excel",
        "application/x-ole-storage",
        "application/CDFV2",
    },
}


def inspect_office(path, extension):
    """Inspect without extracting; reject archives capable of exhausting workers."""
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        if len(items) > 10000 or sum(i.file_size for i in items) > 200 * 1024 * 1024:
            raise ValueError("El archivo Office excede el límite seguro de expansión.")
        for item in items:
            if item.flag_bits & 1 or item.file_size > 50 * 1024 * 1024:
                raise ValueError(
                    "Archivo Office cifrado o componente demasiado grande."
                )
            if item.file_size > max(item.compress_size, 1) * 500:
                raise ValueError("Archivo Office con compresión insegura.")
            if ".." in Path(item.filename).parts or item.filename.startswith("/"):
                raise ValueError("Archivo Office con rutas inseguras.")
            if "vbaproject" in item.filename.lower():
                raise ValueError("No se permiten macros ejecutables.")
        names = set(archive.namelist())
        required = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
        if "[Content_Types].xml" not in names or required not in names:
            raise ValueError("El contenido no corresponde a la extensión Office.")


def inspect_upload(path, filename, allowed_extensions, max_size):
    extension = Path(filename).suffix.lower().lstrip(".")
    allowed = {str(e).lower().lstrip(".") for e in allowed_extensions}
    if extension not in allowed or extension not in MIMES:
        raise ValueError("Formato de archivo no permitido.")
    size = Path(path).stat().st_size
    if size <= 0 or size > int(max_size):
        raise ValueError(
            "El archivo está vacío o supera el límite técnico configurado."
        )
    if os.getenv("WORKFLOW_DESKTOP") == "1":
        from .desktop_services import desktop_mime

        mime = desktop_mime(path, extension)
    else:
        import magic

        mime = magic.from_file(str(path), mime=True)
    if mime not in MIMES[extension]:
        raise ValueError("El contenido real del archivo no coincide con su extensión.")
    if extension in {"docx", "xlsx"}:
        inspect_office(path, extension)
        mime = next(m for m in MIMES[extension] if m != "application/zip")
    if extension in {"doc", "xls"}:
        import olefile

        if not olefile.isOleFile(path):
            raise ValueError(
                "El documento antiguo no tiene un contenedor Office válido."
            )
        with olefile.OleFileIO(path) as container:
            if any(
                any(
                    part.lower()
                    in {"vba", "macros", "_vba_project", "_vba_project_cur"}
                    or part.lower().startswith("__srp_")
                    for part in parts
                )
                for parts in container.listdir()
            ):
                raise ValueError(
                    "No se permiten macros ejecutables en documentos Office antiguos."
                )
            names = {parts[0].lower() for parts in container.listdir() if parts}
            expected = {"worddocument"} if extension == "doc" else {"workbook", "book"}
            if not names.intersection(expected):
                raise ValueError(
                    "El contenido Office antiguo no coincide con su extensión."
                )
        mime = (
            "application/msword" if extension == "doc" else "application/vnd.ms-excel"
        )
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"mime": mime, "sha256": digest.hexdigest(), "size": size}


def scan_file(path):
    if os.getenv("WORKFLOW_DESKTOP") == "1":
        from .desktop_services import scan_defender

        return scan_defender(path)
    try:
        with socket.create_connection(
            (os.getenv("CLAMAV_HOST", "clamav"), int(os.getenv("CLAMAV_PORT", "3310"))),
            timeout=30,
        ) as scanner:
            scanner.settimeout(120)
            scanner.sendall(b"zINSTREAM\0")
            with open(path, "rb") as source:
                for chunk in iter(lambda: source.read(65536), b""):
                    scanner.sendall(struct.pack("!I", len(chunk)) + chunk)
            scanner.sendall(struct.pack("!I", 0))
            response = b""
            while len(response) < 8192:
                part = scanner.recv(1024)
                if not part:
                    break
                response += part
                if b"\0" in response or b"\n" in response:
                    break
            if response.strip(b"\0\r\n") != b"stream: OK":
                raise RuntimeError("Documento rechazado por el análisis antimalware.")
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "Análisis antimalware no disponible; carga bloqueada."
        ) from exc


def _storage(public=False):
    endpoint = (
        (os.getenv("STORAGE_PUBLIC_ENDPOINT") if public else None)
        or os.getenv("STORAGE_ENDPOINT")
        or None
    )
    if (
        os.getenv("APP_ENV", "development") == "production"
        and endpoint
        and not endpoint.startswith("https://")
    ):
        raise RuntimeError("Object storage exige HTTPS en producción.")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("STORAGE_ACCESS_KEY") or None,
        aws_secret_access_key=os.getenv("STORAGE_SECRET_KEY") or None,
        region_name=os.getenv("STORAGE_REGION", "us-east-1"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )


def ensure_bucket():
    """Initialize a private bucket; never loosen an existing bucket policy."""
    if os.getenv("STORAGE_PROVIDER", "s3") == "local":
        from .desktop_services import local_object

        directory = local_object("probe").parent
        directory.mkdir(parents=True, exist_ok=True)
        _encryption_key()
        return {"private": True, "encryption": "AES-256-GCM", "provider": "local"}
    if os.getenv("STORAGE_PROVIDER", "s3") == "azure":
        from azure.core.exceptions import ResourceExistsError

        container = _azure_container()
        try:
            container.create_container(public_access=None)
        except ResourceExistsError:
            pass
        properties = container.get_container_properties()
        if properties.get("public_access"):
            raise RuntimeError(
                "El contenedor Azure permite acceso público; almacenamiento bloqueado."
            )
        _encryption_key()
        return {
            "bucket": os.environ["STORAGE_BUCKET"],
            "private": True,
            "encryption": "AES-256-GCM",
        }
    storage, bucket = _storage(), os.environ["STORAGE_BUCKET"]
    try:
        storage.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if str(exc.response.get("Error", {}).get("Code")) not in {
            "404",
            "NoSuchBucket",
            "NotFound",
        }:
            raise
        region = os.getenv("STORAGE_REGION", "us-east-1")
        options = {"Bucket": bucket}
        if region != "us-east-1":
            options["CreateBucketConfiguration"] = {"LocationConstraint": region}
        storage.create_bucket(**options)
    try:
        policy = storage.get_bucket_policy(Bucket=bucket).get("Policy", "")
        import json

        for statement in json.loads(policy or "{}").get("Statement", []):
            principal = statement.get("Principal")
            if statement.get("Effect") == "Allow" and (
                principal == "*"
                or (isinstance(principal, dict) and "*" in str(principal.values()))
            ):
                raise RuntimeError(
                    "El bucket tiene una política pública; almacenamiento bloqueado."
                )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {
            "NoSuchBucketPolicy",
            "NoSuchPolicy",
        }:
            raise
    acl = storage.get_bucket_acl(Bucket=bucket)
    for grant in acl.get("Grants", []):
        uri = grant.get("Grantee", {}).get("URI", "")
        if uri.endswith("/AllUsers") or uri.endswith("/AuthenticatedUsers"):
            raise RuntimeError(
                "El bucket permite acceso público; almacenamiento bloqueado."
            )
    try:
        storage.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {
            "NotImplemented",
            "UnsupportedOperation",
            "XNotImplemented",
        }:
            raise
    storage.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )
    return {"bucket": bucket, "private": True, "encryption": "AES256"}


def storage_put(path, key, mime):
    if os.getenv("STORAGE_PROVIDER", "s3") == "local":
        from .desktop_services import local_object

        destination = local_object(key)
        # A failed write must not leave an object that looks published.
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
        os.close(fd)
        os.unlink(temporary)
        try:
            _encrypt_file(path, temporary, key.encode("utf-8"))
            # Hard link publishes atomically without replacing an existing key.
            os.link(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return
    if os.getenv("STORAGE_PROVIDER", "s3") == "azure":
        from azure.storage.blob import ContentSettings

        container = _azure_container()
        with tempfile.TemporaryDirectory() as directory:
            encrypted = Path(directory) / "encrypted"
            _encrypt_file(path, encrypted, key.encode("utf-8"))
            with open(encrypted, "rb") as source:
                container.upload_blob(
                    key,
                    source,
                    overwrite=False,
                    content_settings=ContentSettings(
                        content_type="application/octet-stream"
                    ),
                    metadata={"envelope": "WFENC1"},
                )
        return
    _storage().upload_file(
        str(path),
        os.environ["STORAGE_BUCKET"],
        key,
        ExtraArgs={"ContentType": mime, "ServerSideEncryption": "AES256"},
    )


def storage_get(key, path):
    if os.getenv("STORAGE_PROVIDER", "s3") == "local":
        from .desktop_services import local_object

        return _decrypt_file(local_object(key), path, key.encode("utf-8"))
    if os.getenv("STORAGE_PROVIDER", "s3") == "azure":
        with tempfile.TemporaryDirectory() as directory:
            encrypted = Path(directory) / "encrypted"
            with open(encrypted, "xb") as destination:
                os.chmod(encrypted, 0o600)
                for chunk in _azure_container().download_blob(key).chunks():
                    destination.write(chunk)
            _decrypt_file(encrypted, path, key.encode("utf-8"))
        return
    _storage().download_file(os.environ["STORAGE_BUCKET"], key, str(path))


def signed_url(key, filename, expires=120):
    if os.getenv("STORAGE_PROVIDER", "s3") in {"azure", "local"}:
        raise NotImplementedError(
            "Los documentos Azure cifrados requieren descarga temporal autenticada por la API."
        )
    from urllib.parse import quote

    safe = Path(filename).name.replace("\r", "").replace("\n", "")
    return _storage(public=True).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": os.environ["STORAGE_BUCKET"],
            "Key": key,
            "ResponseContentDisposition": "attachment; filename*=UTF-8''"
            + quote(safe, safe=""),
        },
        ExpiresIn=min(max(int(expires), 1), 300),
    )


def _encryption_key():
    try:
        key = base64.b64decode(os.environ["STORAGE_ENCRYPTION_KEY"], validate=True)
    except (KeyError, ValueError) as exc:
        raise RuntimeError(
            "Falta una clave válida de cifrado documental en la configuración segura."
        ) from exc
    if len(key) != 32:
        raise RuntimeError("La clave de cifrado documental debe contener 32 bytes.")
    return key


def _azure_container():
    from azure.storage.blob import BlobServiceClient

    connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    production = os.getenv("APP_ENV", "development") == "production"
    if connection:
        if production:
            fields = dict(
                part.split("=", 1) for part in connection.split(";") if "=" in part
            )
            endpoint = fields.get("BlobEndpoint")
            if (endpoint and not endpoint.startswith("https://")) or (
                not endpoint
                and fields.get("DefaultEndpointsProtocol", "").lower() != "https"
            ):
                raise RuntimeError("Azure Storage exige HTTPS en producción.")
        service = BlobServiceClient.from_connection_string(
            connection, connection_timeout=5, read_timeout=30, retry_total=2
        )
    else:
        from azure.identity import DefaultAzureCredential

        url = os.environ["AZURE_STORAGE_ACCOUNT_URL"]
        if not url.startswith("https://") and production:
            raise RuntimeError("Azure Storage exige HTTPS en producción.")
        service = BlobServiceClient(
            url,
            credential=DefaultAzureCredential(),
            connection_timeout=5,
            read_timeout=30,
            retry_total=2,
        )
    return service.get_container_client(os.environ["STORAGE_BUCKET"])


def storage_available():
    """Read-only health probe; never include connection strings in the result."""
    if os.getenv("STORAGE_PROVIDER", "s3") == "local":
        from .desktop_services import local_object

        directory = local_object("probe").parent
        _encryption_key()
        if not directory.is_dir() or not os.access(directory, os.R_OK | os.W_OK):
            raise RuntimeError("Almacenamiento local no disponible.")
    elif os.getenv("STORAGE_PROVIDER", "s3") == "azure":
        properties = _azure_container().get_container_properties()
        if properties.get("public_access"):
            raise RuntimeError("El contenedor documental no es privado.")
        _encryption_key()
    else:
        _storage().head_bucket(Bucket=os.environ["STORAGE_BUCKET"])
    return True


def _encrypt_file(source, destination, object_context=b""):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    nonce = os.urandom(12)
    header = b"WFENC1" + nonce
    encryptor = Cipher(algorithms.AES(_encryption_key()), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header + object_context)
    with open(source, "rb") as plain, open(destination, "xb") as encrypted:
        os.chmod(destination, 0o600)
        encrypted.write(header)
        for chunk in iter(lambda: plain.read(1024 * 1024), b""):
            encrypted.write(encryptor.update(chunk))
        encrypted.write(encryptor.finalize())
        encrypted.write(encryptor.tag)


def _decrypt_file(source, destination, object_context=b""):
    """Publish plaintext only after tag verification; partial files remain private."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    size = Path(source).stat().st_size
    if size < 34:
        raise RuntimeError("Documento cifrado incompleto.")
    fd, temporary = tempfile.mkstemp(
        prefix=".workflow-decrypt-", dir=Path(destination).parent
    )
    try:
        with open(source, "rb") as encrypted, os.fdopen(fd, "wb") as plain:
            header = encrypted.read(18)
            if header[:6] != b"WFENC1":
                raise RuntimeError("Formato de cifrado documental desconocido.")
            encrypted.seek(-16, os.SEEK_END)
            tag = encrypted.read(16)
            encrypted.seek(18)
            decryptor = Cipher(
                algorithms.AES(_encryption_key()), modes.GCM(header[6:], tag)
            ).decryptor()
            decryptor.authenticate_additional_data(header + object_context)
            remaining = size - 34
            while remaining:
                chunk = encrypted.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise RuntimeError("Documento cifrado incompleto.")
                plain.write(decryptor.update(chunk))
                remaining -= len(chunk)
            plain.write(decryptor.finalize())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
