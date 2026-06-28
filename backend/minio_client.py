import os
import io
from minio import Minio

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET_NAME = "studia-pdfs"


def get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket():
    client = get_minio_client()
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)


def upload_pdf(object_name: str, data: bytes) -> str:
    return upload_bytes(object_name, data, "application/pdf")


def upload_bytes(object_name: str, data: bytes, content_type: str) -> str:
    """Sobe bytes genéricos ao bucket (reusa o bucket dos PDFs com prefixo no nome)."""
    client = get_minio_client()
    ensure_bucket()
    client.put_object(
        BUCKET_NAME,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{BUCKET_NAME}/{object_name}"


def download_pdf(object_name: str) -> bytes:
    return download_bytes(object_name)


def download_bytes(object_name: str) -> bytes:
    """Baixa os bytes de um objeto do bucket. Levanta se não existir.

    Usado para servir imagens do fórum PELO backend (stream), em vez de
    redirecionar o navegador para a URL presigned do MinIO — cujo host
    (`minio:9000`) só resolve dentro da rede dos containers.
    """
    client = get_minio_client()
    response = client.get_object(BUCKET_NAME, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def get_presigned_url(object_name: str, expires_hours: int = 1) -> str:
    from datetime import timedelta
    client = get_minio_client()
    return client.presigned_get_object(
        BUCKET_NAME, object_name, expires=timedelta(hours=expires_hours)
    )
