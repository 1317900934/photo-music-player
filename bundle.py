# -*- coding: utf-8 -*-
"""PMB（Photo Music Bundle）自定义打包格式的读写模块。

.pmb 本质上是一个 zip 包，内部结构如下：

    manifest.json        —— 元数据（格式标识、标题、图片/音乐清单）
    assets/000_xxx.jpg   —— 图片文件
    assets/001_yyy.mp3   —— 音乐文件

识别规则：zip 包内必须包含 manifest.json，且其中 format 字段等于 FORMAT_MAGIC。
"""
import json
import os
import re
import shutil
import tempfile
import zipfile

FORMAT_MAGIC = "photo-music-bundle"
FORMAT_VERSION = 1

_INVALID_FS = re.compile(r'[\\/:*?"<>|\r\n\t]')

MANIFEST_NAME = "manifest.json"
ASSET_DIR = "assets"


class BundleError(Exception):
    """打包文件无效或损坏时抛出。"""


def _unique_stored_name(index: int, original_path: str) -> str:
    """生成 assets 内的唯一存储名，避免不同目录的同名文件互相覆盖。"""
    base = os.path.basename(original_path)
    return f"{index:03d}_{base}"


def create_bundle(title: str, image_paths, music_paths, output_path: str) -> str:
    """把图片和音乐打包成 .pmb 文件，返回输出路径。"""
    manifest = {
        "format": FORMAT_MAGIC,
        "version": FORMAT_VERSION,
        "title": (title or "未命名相册").strip(),
        "images": [],
        "musics": [],
    }
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, p in enumerate(image_paths):
            stored = _unique_stored_name(i, p)
            zf.write(p, f"{ASSET_DIR}/{stored}")
            manifest["images"].append(
                {"name": os.path.basename(p), "path": f"{ASSET_DIR}/{stored}"}
            )
        for i, p in enumerate(music_paths):
            stored = _unique_stored_name(len(image_paths) + i, p)
            zf.write(p, f"{ASSET_DIR}/{stored}")
            manifest["musics"].append(
                {"name": os.path.basename(p), "path": f"{ASSET_DIR}/{stored}"}
            )
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
    return output_path


def is_bundle(path: str) -> bool:
    """快速判断一个文件是否是合法的 .pmb 打包文件。"""
    try:
        with zipfile.ZipFile(path) as zf:
            if MANIFEST_NAME not in zf.namelist():
                return False
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            return manifest.get("format") == FORMAT_MAGIC
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, OSError):
        return False


def _safe_dirname(name: str) -> str:
    """把相册标题清洗成可用的 Windows 文件夹名。"""
    name = _INVALID_FS.sub("_", name).strip(" .")
    return name or "未命名相册"


def extract_bundle(path: str, output_dir: str) -> str:
    """把 .pmb 解包还原为独立文件夹，恢复原始图片/音乐文件名。

    在 output_dir 下创建 <相册标题> 子文件夹，内部含：
        图片/       —— 还原的图片（原始文件名）
        音乐/       —— 还原的音乐（原始文件名）
        manifest.json —— 元数据备份

    返回创建的文件夹路径。
    """
    if not is_bundle(path):
        raise BundleError("这不是有效的 .pmb 音乐相册文件")
    try:
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
        raise BundleError(f"文件损坏或无法读取：{e}")

    title = (manifest.get("title") or "未命名相册").strip()
    folder = os.path.join(output_dir, _safe_dirname(title))
    if os.path.exists(folder):
        suffix = 2
        while os.path.exists(f"{folder} ({suffix})"):
            suffix += 1
        folder = f"{folder} ({suffix})"

    img_dir = os.path.join(folder, "图片")
    os.makedirs(img_dir, exist_ok=True)
    # 只有打包了音乐才创建"音乐"文件夹
    music_dir = None
    if manifest.get("musics"):
        music_dir = os.path.join(folder, "音乐")
        os.makedirs(music_dir, exist_ok=True)

    with zipfile.ZipFile(path) as zf:
        for item in manifest.get("images", []):
            stored = item.get("path")
            if not stored:
                continue
            zf.extract(stored, img_dir)
            dst = os.path.join(img_dir, os.path.basename(item.get("name") or stored))
            src = os.path.join(img_dir, stored)
            if os.path.normpath(src) != os.path.normpath(dst):
                os.replace(src, dst)
        if music_dir:
            for item in manifest.get("musics", []):
                stored = item.get("path")
                if not stored:
                    continue
                zf.extract(stored, music_dir)
                dst = os.path.join(music_dir, os.path.basename(item.get("name") or stored))
                src = os.path.join(music_dir, stored)
                if os.path.normpath(src) != os.path.normpath(dst):
                    os.replace(src, dst)
        zf.extract(MANIFEST_NAME, folder)

    # 清理解压后遗留的空目录（如 assets/）
    for base in (img_dir, music_dir):
        if base is None:
            continue
        for dirpath, _dirnames, filenames in os.walk(base, topdown=False):
            if not _dirnames and not filenames:
                os.rmdir(dirpath)
    return folder


class Bundle:
    """打开后的 .pmb 包：完成校验并把资源解压到临时目录供播放器读取。"""

    def __init__(self, path: str):
        self.path = path
        self._tmpdir = None
        self._manifest = None
        self._load()

    def _load(self):
        if not is_bundle(self.path):
            raise BundleError("这不是有效的 .pmb 音乐相册文件")
        try:
            with zipfile.ZipFile(self.path) as zf:
                self._manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
                self._tmpdir = tempfile.mkdtemp(prefix="pmb_")
                zf.extractall(self._tmpdir)
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
            self.close()
            raise BundleError(f"文件损坏或无法读取：{e}")

        self.title = self._manifest.get("title", "未命名相册")
        self.images = list(self._manifest.get("images", []))
        self.musics = list(self._manifest.get("musics", []))
        if not self.images:
            self.close()
            raise BundleError("打包文件中没有图片")

    def asset_path(self, rel_path: str) -> str:
        """把包内相对路径映射到本地解压后的绝对路径。"""
        return os.path.join(self._tmpdir, rel_path)

    def close(self):
        """释放临时目录（停止播放后再调用）。"""
        if self._tmpdir and os.path.isdir(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
