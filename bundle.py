# -*- coding: utf-8 -*-
"""PMB（Photo Music Bundle）自定义打包格式的读写模块。

.pmb 本质上是一个 zip 包，内部结构如下：

    manifest.json        —— 元数据（格式标识、标题、图片/音乐清单）
    assets/xxx.jpg       —— 图片文件（保持原始文件名）
    assets/yyy.mp3       —— 音乐文件

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
NUMBER_PREFIX_RE = re.compile(r"^\d{4}_")

MANIFEST_NAME = "manifest.json"
ASSET_DIR = "assets"


class BundleError(Exception):
    """打包文件无效或损坏时抛出。"""


def _unique_stored_name(base: str, taken: set) -> str:
    """生成 assets 内的唯一存储名。

    默认保持原始文件名不变；仅当 zip 内已存在同名条目时追加
    " (2)"、" (3)" 后缀，避免同名文件互相覆盖。
    """
    name = base
    i = 2
    while name in taken:
        stem, ext = os.path.splitext(base)
        name = f"{stem} ({i}){ext}"
        i += 1
    taken.add(name)
    return name


def numbered_stored_name(index: int, name: str) -> str:
    """按 1 起始序号生成包内存储名：0001_原始名、0002_原始名……

    只负责在原始名前面加序号前缀；原始名（含用户自带的数字下划线）原样保留。
    """
    return f"{index:04d}_{name}"


def strip_stored_sequence_prefix(stored_name: str, original_name: str) -> str:
    """去掉包内存储名最前面的序号前缀（如 0001_）。

    只有存储名确实是「序号_原始名」形式时才去掉，普通文件名
    （例如用户本来就叫 2024_旅行.png）原样保留，以此兼容旧版
    没有序号前缀的 pmb 文件。
    """
    m = NUMBER_PREFIX_RE.match(stored_name)
    if m and stored_name[m.end():] == original_name:
        return stored_name[m.end():]
    return stored_name


def create_bundle(
    title: str,
    image_paths,
    music_paths,
    output_path: str,
    image_names=None,
    music_names=None,
) -> str:
    """把图片和音乐打包成 .pmb 文件，返回输出路径。

    图片、音乐分别按列表顺序从 0001 开始编号，包内存储名形如
    "0001_原始名.jpg"；manifest 中的 name 始终保存原始文件名，
    供界面显示和拆解时还原。image_names / music_names 可选，传入时
    manifest 的 name 使用这些界面显示名（允许重名），包内物理文件名
    仍按各自磁盘文件名保持唯一。
    """
    manifest = {
        "format": FORMAT_MAGIC,
        "version": FORMAT_VERSION,
        "title": (title or "未命名相册").strip(),
        "images": [],
        "musics": [],
    }
    taken = set()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, p in enumerate(image_paths, 1):
            disk_name = os.path.basename(p)
            display = (
                image_names[i - 1]
                if image_names and i - 1 < len(image_names)
                else disk_name
            )
            stored = _unique_stored_name(numbered_stored_name(i, disk_name), taken)
            zf.write(p, f"{ASSET_DIR}/{stored}")
            manifest["images"].append(
                {"name": display, "path": f"{ASSET_DIR}/{stored}"}
            )
        for i, p in enumerate(music_paths, 1):
            disk_name = os.path.basename(p)
            display = (
                music_names[i - 1]
                if music_names and i - 1 < len(music_names)
                else disk_name
            )
            stored = _unique_stored_name(numbered_stored_name(i, disk_name), taken)
            zf.write(p, f"{ASSET_DIR}/{stored}")
            manifest["musics"].append(
                {"name": display, "path": f"{ASSET_DIR}/{stored}"}
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
        img_taken = set()
        for item in manifest.get("images", []):
            stored = item.get("path")
            if not stored:
                continue
            zf.extract(stored, img_dir)
            # 用 manifest 里的原始名还原文件；多个文件原始名相同时，
            # 追加 " (2)" 后缀避免互相覆盖
            original = os.path.basename(item.get("name") or stored)
            dst_name = original
            i = 2
            while dst_name in img_taken:
                stem, ext = os.path.splitext(original)
                dst_name = f"{stem} ({i}){ext}"
                i += 1
            img_taken.add(dst_name)
            dst = os.path.join(img_dir, dst_name)
            src = os.path.join(img_dir, stored)
            if os.path.normpath(src) != os.path.normpath(dst):
                os.replace(src, dst)
        if music_dir:
            music_taken = set()
            for item in manifest.get("musics", []):
                stored = item.get("path")
                if not stored:
                    continue
                zf.extract(stored, music_dir)
                original = os.path.basename(item.get("name") or stored)
                dst_name = original
                i = 2
                while dst_name in music_taken:
                    stem, ext = os.path.splitext(original)
                    dst_name = f"{stem} ({i}){ext}"
                    i += 1
                music_taken.add(dst_name)
                dst = os.path.join(music_dir, dst_name)
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
