"""
Cloudinary helper for Verdant.
Uploads files to Cloudinary and returns secure URLs.
"""
import cloudinary
import cloudinary.uploader

# Configure Cloudinary
cloudinary.config(
    cloud_name='dhooqjy40',
    api_key='978447867729474',
    api_secret='hEKUyFrxkIq8o3h_S2FI7ZKQ2LQ',
    secure=True
)


def upload_image(file_obj, folder: str, public_id: str = None) -> str:
    """
    Upload a file-like object to Cloudinary.

    Args:
        file_obj: werkzeug FileStorage object
        folder:   Cloudinary folder, e.g. 'verdant/products'
        public_id: optional custom public ID

    Returns:
        Secure URL string, or '' on failure.
    """
    try:
        file_obj.seek(0)
        options = {'folder': folder, 'resource_type': 'image'}
        if public_id:
            options['public_id'] = public_id

        result = cloudinary.uploader.upload(file_obj, **options)
        return result.get('secure_url', '')
    except Exception as e:
        print(f"[Cloudinary] Upload error: {e}")
        return ''


def delete_image(url: str):
    """Delete an image from Cloudinary by its URL."""
    try:
        if not url or 'cloudinary.com' not in url:
            return
        # Extract public_id from URL
        # URL format: https://res.cloudinary.com/CLOUD/image/upload/vXXX/FOLDER/PUBLIC_ID.ext
        parts = url.split('/upload/')
        if len(parts) < 2:
            return
        path = parts[1]
        # Remove version prefix (v1234567/)
        if path.startswith('v') and '/' in path:
            path = path.split('/', 1)[1]
        # Remove extension
        public_id = path.rsplit('.', 1)[0]
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print(f"[Cloudinary] Delete error: {e}")
