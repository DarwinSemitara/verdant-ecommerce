"""
Firebase Storage helper for Verdant.
Uploads files to Firebase Storage and returns public download URLs.
"""
import uuid
import os
from firebase_admin import storage


def _bucket():
    """Get the default Firebase Storage bucket."""
    return storage.bucket()


def upload_file(file_obj, folder: str, username: str, prefix: str = 'file') -> str:
    """
    Upload a file-like object to Firebase Storage.

    Args:
        file_obj: werkzeug FileStorage object
        folder:   storage folder, e.g. 'products', 'profiles', 'store', 'documents'
        username: used to namespace the filename
        prefix:   short label, e.g. 'product', 'var', 'profile', 'store'

    Returns:
        Public download URL string, or '' on failure.
    """
    try:
        filename = file_obj.filename or ''
        if '.' not in filename:
            return ''
        ext = filename.rsplit('.', 1)[1].lower()
        allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
        if ext not in allowed:
            return ''

        unique_name = f"{username}_{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
        blob_path = f"{folder}/{unique_name}"

        bucket = _bucket()
        blob = bucket.blob(blob_path)

        file_obj.seek(0)
        blob.upload_from_file(file_obj, content_type=_content_type(ext))
        blob.make_public()

        return blob.public_url
    except Exception as e:
        print(f"[Firebase Storage] Upload error: {e}")
        return ''


def delete_file(url: str):
    """Delete a file from Firebase Storage by its public URL."""
    try:
        if not url or 'storage.googleapis.com' not in url:
            return
        # Extract blob path from URL
        # URL format: https://storage.googleapis.com/BUCKET/BLOB_PATH
        parts = url.split('storage.googleapis.com/')
        if len(parts) < 2:
            return
        blob_path = parts[1].split('?')[0]
        # Remove bucket name prefix
        bucket_name = _bucket().name
        if blob_path.startswith(bucket_name + '/'):
            blob_path = blob_path[len(bucket_name) + 1:]
        blob = _bucket().blob(blob_path)
        blob.delete()
    except Exception as e:
        print(f"[Firebase Storage] Delete error: {e}")


def _content_type(ext: str) -> str:
    return {
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'png': 'image/png', 'gif': 'image/gif',
        'webp': 'image/webp', 'pdf': 'application/pdf',
    }.get(ext, 'application/octet-stream')
