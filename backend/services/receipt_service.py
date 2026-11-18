"""凭证图片存取服务。

职责：把用户上传的票据/截图安全地落到磁盘，并把元信息交给上层入库。

三条硬性约束：

1. **二进制不进数据库**。SQLite 存 BLOB 会让库迅速膨胀、拖慢备份与迁移，
   所以库里只存相对路径 + SHA-256 + 大小 + 尺寸 + MIME，文件放 ``instance/uploads/``。
2. **必须剥离 EXIF**。手机拍的照片带 GPS 坐标，直接存等于把家庭住址写进账本；
   EXIF 里还可能有设备序列号等标识。这里统一「解码 → 转正方向 → 重编码」，
   新文件不携带任何原始元数据（仅保留 ICC 色彩配置，避免广色域照片偏色）。
3. **按内容哈希命名**。不保留原始文件名（"张三的电费.png" 本身就是隐私泄露），
   磁盘用 ``<sha256 前2位>/<sha256>.<ext>``。相同内容天然只存一份——
   同张截图重复上传不会占用额外空间。
"""
import hashlib
import io
import os
import tempfile
import time
from datetime import datetime

from PIL import Image, ImageOps, UnidentifiedImageError

# 上限 10MB：手机截图通常 200KB~3MB，超过这个量级基本不是凭证图
MAX_BYTES = 10 * 1024 * 1024
# 约 4000 万像素，超出视为异常图片（防解压炸弹）
Image.MAX_IMAGE_PIXELS = 40_000_000

# 允许的格式 -> (扩展名, MIME)
_ALLOWED = {
    'JPEG': ('jpg', 'image/jpeg'),
    'PNG': ('png', 'image/png'),
    'WEBP': ('webp', 'image/webp'),
}
# 按格式给重编码参数：JPEG 需要质量控制，其余用无损
_SAVE_OPTIONS = {
    'JPEG': {'quality': 90, 'optimize': True, 'progressive': True},
    'PNG': {'optimize': True},
    'WEBP': {'quality': 90, 'method': 4},
}


class ReceiptError(Exception):
    """凭证处理失败，message 可直接展示给用户。"""


def _read_limited(stream):
    """分块读取并限制总大小，避免恶意超大文件打满内存。"""
    buf = io.BytesIO()
    total = 0
    while True:
        chunk = stream.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise ReceiptError(f'图片超过 {MAX_BYTES // 1024 // 1024}MB 上限')
        buf.write(chunk)
    if total == 0:
        raise ReceiptError('上传内容为空')
    buf.seek(0)
    return buf


def _sanitize(raw_stream):
    """解码、转正方向、重编码，返回 (bytes, 格式, 宽, 高)。重编码后不携带任何原始 EXIF。"""
    try:
        with Image.open(_read_limited(raw_stream)) as probe:
            fmt = (probe.format or '').upper()
            if fmt not in _ALLOWED:
                raise ReceiptError(
                    f'不支持的图片格式：{fmt or "未知"}（仅支持 JPG / PNG / WEBP）'
                )
            probe.verify()  # 结构校验，verify 后对象不可再用
    except ReceiptError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ReceiptError('无法识别的图片文件，请确认是有效的 JPG / PNG / WEBP')

    raw_stream.seek(0)
    try:
        with Image.open(_read_limited(raw_stream)) as img:
            fmt = (img.format or '').upper()
            if fmt not in _ALLOWED:
                raise ReceiptError(f'不支持的图片格式：{fmt}（仅支持 JPG / PNG / WEBP）')
            # 按 EXIF Orientation 旋转到正确方向，返回的图像不再需要该标签
            img = ImageOps.exif_transpose(img)
            icc = img.info.get('icc_profile')
            width, height = img.size
            if width < 1 or height < 1:
                raise ReceiptError('图片尺寸异常')

            if fmt == 'JPEG' and img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            elif fmt == 'WEBP' and img.mode == 'P':
                img = img.convert('RGBA')

            out = io.BytesIO()
            options = dict(_SAVE_OPTIONS.get(fmt, {}))
            if icc:
                options['icc_profile'] = icc
            img.save(out, format=fmt, **options)
            return out.getvalue(), fmt, width, height
    except ReceiptError:
        raise
    except Image.DecompressionBombError:
        raise ReceiptError('图片像素过大，已拒绝保存')
    except (UnidentifiedImageError, OSError, ValueError):
        raise ReceiptError('图片解析失败，可能文件已损坏')


def save_receipt(source, upload_dir):
    """保存一张凭证图片，返回落库所需的元信息。

    ``source`` 可以是文件路径（str）或任何带 ``read()`` 的二进制流（如 Flask 的 FileStorage）。
    返回值含 ``rel_path``（相对 upload_dir，正斜杠）、``sha256``、``size_bytes``、
    ``width``、``height``、``mime``、``format``、``deduplicated``（内容已存在时为 True）。
    """
    if isinstance(source, (str, os.PathLike)):
        with open(source, 'rb') as handle:
            data, fmt, width, height = _sanitize(handle)
    else:
        data, fmt, width, height = _sanitize(source)

    sha = hashlib.sha256(data).hexdigest()
    ext, mime = _ALLOWED[fmt]
    rel_path = f'{sha[:2]}/{sha}.{ext}'
    abs_path = os.path.join(upload_dir, sha[:2], f'{sha}.{ext}')

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    deduplicated = os.path.isfile(abs_path) and os.path.getsize(abs_path) == len(data)
    if not deduplicated:
        # 先写临时文件再原子替换：避免并发或中断留下半张图
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(abs_path), suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
            os.replace(tmp_path, abs_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    return {
        'rel_path': rel_path,
        'sha256': sha,
        'size_bytes': len(data),
        'width': width,
        'height': height,
        'mime': mime,
        'format': fmt,
        'deduplicated': deduplicated,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
    }


def resolve_stored_path(upload_dir, rel_path):
    """把库里的相对路径还原为绝对路径，并确保没有越出上传根目录。

    路径来自数据库，理论上可信；但库文件可能被手工改动，这里仍做一次越界校验，
    防止 ``../../.env`` 之类的路径读到凭证目录之外的文件。
    """
    if not rel_path:
        return None
    root = os.path.realpath(upload_dir)
    candidate = os.path.realpath(os.path.join(root, str(rel_path).replace('/', os.sep)))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate if os.path.isfile(candidate) else None


def remove_stored_file(upload_dir, rel_path):
    """删除磁盘上的凭证文件，成功返回 True。仅在确认无其他记录引用时调用。"""
    abs_path = resolve_stored_path(upload_dir, rel_path)
    if not abs_path:
        return False
    # Windows 上刚被 send_file 读过、或杀毒软件正在扫描时文件会短暂被占用，
    # 直接删会 PermissionError；退让重试比让用户看到「文件未删除」更合理
    for attempt in range(3):
        try:
            os.remove(abs_path)
            break
        except FileNotFoundError:
            return False
        except PermissionError:
            if attempt == 2:
                return False
            time.sleep(0.05)
        except OSError:
            return False
    # 缩略图生命周期绑在原图上，原图没了就没人会再引用它们
    remove_thumbnails(upload_dir, rel_path)
    return True


# 缩略图缓存目录（位于上传根目录下，带点前缀，gc 会跳过）
THUMB_DIRNAME = '.thumbs'
THUMB_MIN, THUMB_MAX, THUMB_DEFAULT = 48, 512, 160


def remove_thumbnails(upload_dir, rel_path):
    """删除某张原图对应的全部尺寸缩略图，返回删除个数。"""
    stem = os.path.splitext(os.path.basename(str(rel_path or '')))[0]
    if not stem:
        return 0
    folder = os.path.join(os.path.realpath(upload_dir), THUMB_DIRNAME)
    if not os.path.isdir(folder):
        return 0
    removed = 0
    for name in os.listdir(folder):
        if name.startswith(f'{stem}_') and name.endswith('.jpg'):
            try:
                os.remove(os.path.join(folder, name))
                removed += 1
            except OSError:
                pass
    return removed


def make_thumbnail(upload_dir, rel_path, size=THUMB_DEFAULT):
    """生成或复用缩略图，返回绝对路径；源文件缺失或解码失败返回 None。

    列表页直接拉原图会把几十张手机照片（数 MB/张）灌进浏览器，所以这里按需
    生成小图并落盘缓存。缩略图以原文件哈希命名，内容变则名字变，天然不会读到旧图。
    """
    source = resolve_stored_path(upload_dir, rel_path)
    if not source:
        return None

    try:
        size = max(THUMB_MIN, min(int(size), THUMB_MAX))
    except (TypeError, ValueError):
        size = THUMB_DEFAULT

    root = os.path.realpath(upload_dir)
    stem = os.path.splitext(os.path.basename(source))[0]
    target = os.path.join(root, THUMB_DIRNAME, f'{stem}_{size}.jpg')
    if os.path.isfile(target):
        return target

    try:
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            # 透明图铺白底，避免 JPEG 把 alpha 压成黑块
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
                canvas = Image.new('RGB', img.size, (255, 255, 255))
                canvas.paste(img, mask=img.getchannel('A'))
                img = canvas
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((size, size), Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=82, optimize=True, progressive=True)

            os.makedirs(os.path.dirname(target), exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target), suffix='.tmp')
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(buffer.getvalue())
                os.replace(tmp_path, target)
            except OSError:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        return target
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None

