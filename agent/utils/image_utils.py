"""
图片处理工具模块。

提供图片压缩、格式转换等功能，用于多模态消息处理。
"""

import base64
import io
import requests
from typing import Tuple, Optional, List

from loguru import logger
from PIL import Image

from agent.config.configloader import GLOBAL_CONFIG


DEFAULT_MAX_SIZE = 1024
DEFAULT_QUALITY = 85
MAX_FILE_SIZE = 20 * 1024 * 1024


def _get_config() -> Tuple[int, int, int]:
    """从配置文件获取压缩参数。"""
    max_size = GLOBAL_CONFIG.get("image.max_size", DEFAULT_MAX_SIZE)
    quality = GLOBAL_CONFIG.get("image.quality", DEFAULT_QUALITY)
    max_file_size_mb = GLOBAL_CONFIG.get("image.max_file_size_mb", 20)
    max_file_size = max_file_size_mb * 1024 * 1024
    return max_size, quality, max_file_size


def compress_image(
    image_source: str,
    max_size: int = None,
    quality: int = None,
    max_file_size: int = None
) -> str:
    """
    压缩图片并返回 Base64 格式（同步版本）。
    
    支持多种输入格式：
    - Base64 格式: data:image/jpeg;base64,/9j/4AAQ...
    - URL 格式: https://example.com/image.jpg
    
    Args:
        image_source: 图片源（Base64 或 URL）
        max_size: 最大边长（像素），默认从配置读取，默认 1024
        quality: JPEG 质量（1-100），默认从配置读取，默认 85
        max_file_size: 最大文件大小（字节），默认从配置读取，默认 20MB
        
    Returns:
        Base64 格式字符串: data:image/jpeg;base64,...
    """
    config_max_size, config_quality, config_max_file_size = _get_config()
    max_size = max_size or config_max_size
    quality = quality or config_quality
    max_file_size = max_file_size or config_max_file_size
    
    try:
        if image_source.startswith('data:'):
            return _compress_base64(image_source, max_size, quality, max_file_size)
        elif image_source.startswith(('http://', 'https://')):
            return _compress_url(image_source, max_size, quality, max_file_size)
        else:
            logger.warning(f"[图片] 不支持的图片源格式: {image_source[:50]}...")
            return image_source
    except Exception as e:
        logger.error(f"[图片] 压缩失败: {e}")
        return image_source


def compress_images(
    images: List[str],
    max_size: int = None,
    quality: int = None
) -> List[str]:
    """
    批量压缩图片列表。
    
    Args:
        images: 图片源列表
        max_size: 最大边长
        quality: JPEG 质量
        
    Returns:
        压缩后的 Base64 图片列表
    """
    if not images:
        return []
    
    config_max_size, config_quality, _ = _get_config()
    max_size = max_size or config_max_size
    quality = quality or config_quality
    
    logger.info(f"[图片] 开始压缩 {len(images)} 张图片，参数: max_size={max_size}, quality={quality}")
    
    compressed = []
    total_original = 0
    total_compressed = 0
    
    for i, img in enumerate(images):
        try:
            result = compress_image(img, max_size, quality)
            if result.startswith('data:'):
                orig_len = len(img) if img.startswith('data:') else 0
                comp_len = len(result)
                total_original += orig_len
                total_compressed += comp_len
                logger.info(f"[图片] 第 {i+1}/{len(images)} 张压缩完成: {orig_len} -> {comp_len} bytes")
            compressed.append(result)
        except Exception as e:
            logger.warning(f"[图片] 第 {i+1} 张压缩失败，保留原图: {e}")
            compressed.append(img)
    
    if total_original > 0:
        ratio = (1 - total_compressed / total_original) * 100
        logger.info(f"[图片] 压缩完成: {total_original} -> {total_compressed} bytes，节省 {ratio:.1f}%")
    
    return compressed


def _compress_base64(base64_data: str, max_size: int, quality: int, max_file_size: int) -> str:
    """压缩 Base64 格式图片。"""
    mime_type, image_bytes = _parse_base64(base64_data)
    compressed_bytes, new_size = _compress_bytes(image_bytes, max_size, quality, max_file_size)
    
    result = f"data:image/jpeg;base64,{base64.b64encode(compressed_bytes).decode('utf-8')}"
    logger.debug(f"[图片] Base64 压缩: {len(image_bytes)} -> {len(compressed_bytes)} bytes")
    return result


def _compress_url(url: str, max_size: int, quality: int, max_file_size: int) -> str:
    """下载并压缩 URL 图片。"""
    logger.info(f"[图片] 下载 URL 图片: {url[:50]}...")
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        raise IOError(f"图片下载失败: HTTP {response.status_code}")
    
    image_bytes = response.content
    compressed_bytes, new_size = _compress_bytes(image_bytes, max_size, quality, max_file_size)
    
    result = f"data:image/jpeg;base64,{base64.b64encode(compressed_bytes).decode('utf-8')}"
    logger.debug(f"[图片] URL 压缩: {len(image_bytes)} -> {len(compressed_bytes)} bytes")
    return result


def _parse_base64(base64_data: str) -> Tuple[str, bytes]:
    """解析 Base64 图片数据，返回 (MIME类型, 字节数据)。"""
    if not base64_data.startswith('data:'):
        raise ValueError("无效的 Base64 数据格式")
    
    header, data = base64_data.split(',', 1)
    mime_match = header[5:].split(';')[0]
    mime_type = mime_match if mime_match.startswith('image/') else 'image/jpeg'
    
    image_bytes = base64.b64decode(data)
    return mime_type, image_bytes


def _compress_bytes(image_bytes: bytes, max_size: int, quality: int, max_file_size: int) -> Tuple[bytes, tuple]:
    """压缩图片字节数据，返回 (压缩后字节, 新尺寸)。"""
    img = Image.open(io.BytesIO(image_bytes))
    
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    original_size = img.size
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        logger.debug(f"[图片] 缩放: {original_size} -> {new_size}")
    
    output = io.BytesIO()
    current_quality = quality
    
    while current_quality >= 50:
        output.seek(0)
        output.truncate()
        img.save(output, format='JPEG', quality=current_quality, optimize=True)
        
        if output.tell() <= max_file_size:
            break
        
        current_quality -= 10
    
    output.seek(0)
    return output.read(), img.size


def get_image_info(image_source: str) -> dict:
    """获取图片基本信息。"""
    try:
        if image_source.startswith('data:'):
            _, image_bytes = _parse_base64(image_source)
        else:
            return {"error": "URL 图片需要下载才能获取信息"}
        
        img = Image.open(io.BytesIO(image_bytes))
        return {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
            "size_bytes": len(image_bytes)
        }
    except Exception as e:
        return {"error": str(e)}
