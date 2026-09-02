#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a password-encrypted, static-hosting-safe private workbench release.

The source must be a checked ``private-portable`` schema-2 release.  Personal
HTML and every referenced local asset are first collapsed into one HTML byte
stream, then encrypted with PBKDF2-HMAC-SHA256 + AES-256-GCM.  CloudBase only
receives a public login shell, ciphertext, and a non-sensitive manifest.

The passphrase is never accepted on the command line.  ``--initialize-secret``
opens a local masked GUI and stores the passphrase with Windows DPAPI outside
the project.  Normal Agent runs can reuse that DPAPI-protected secret without
printing it or writing it to a receipt.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SCRIPT_VERSION = "1.0.0"
SOURCE_SCHEMA = 2
SOURCE_KIND = "lzheng-fitness-workbench-release"
SOURCE_PRODUCER = "Prepare-FitnessWorkbenchRelease.py"
OUTPUT_SCHEMA = 1
OUTPUT_KIND = "lzheng-fitness-workbench-encrypted-release"
OUTPUT_PRODUCER = "Prepare-FitnessWorkbenchEncryptedRelease.py"
PAYLOAD_NAME = "private-payload.json"
MANIFEST_NAME = "release-manifest.json"
ITERATIONS = 600_000
AAD = b"lzheng-fitness-workbench-private-v1"
DPAPI_ENTROPY = b"lzheng-fitness-workbench-dpapi-v1"
PRIVATE_MARKERS = ("obsidian://", "notion://", "E:\\obsidian", "C:\\Users\\", "/Users/", "/home/")


class ReleaseError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_secret_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "LzhengFitness" / "cloudbase-private.secret.json"


def _blob(value: bytes) -> tuple[DATA_BLOB, Any]:
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    return DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi_libraries() -> tuple[Any, Any]:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def dpapi_protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise ReleaseError("私人发布密钥只允许存入 Windows DPAPI")
    crypt32, kernel32 = _dpapi_libraries()
    source, source_buffer = _blob(value)
    entropy, entropy_buffer = _blob(DPAPI_ENTROPY)
    output = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(source), "Lzheng Fitness", ctypes.byref(entropy), None, None, 0x1, ctypes.byref(output)):
        raise ReleaseError("Windows DPAPI 无法保护私人发布密钥")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
        del source_buffer, entropy_buffer


def dpapi_unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise ReleaseError("私人发布密钥只允许从 Windows DPAPI 读取")
    crypt32, kernel32 = _dpapi_libraries()
    source, source_buffer = _blob(value)
    entropy, entropy_buffer = _blob(DPAPI_ENTROPY)
    output = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(output)):
        raise ReleaseError("Windows DPAPI 无法解密私人发布密钥；请使用创建它的 Windows 用户")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
        del source_buffer, entropy_buffer


def strong_passphrase(value: str) -> bool:
    if len(value) < 24 or len(value) > 256:
        return False
    classes = sum(bool(re.search(pattern, value)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    return classes == 4


def initialize_secret(path: Path, rotate: bool = False) -> None:
    if path.exists() and not rotate:
        raise ReleaseError("私人发布密钥已经存在；为避免旧网站失效，本工具拒绝静默覆盖")
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
    except ImportError as exc:
        raise ReleaseError("当前 Python 缺少本地安全输入窗口") from exc
    root = tk.Tk()
    root.withdraw()
    try:
        first = simpledialog.askstring("健身工作台私有密码", "请粘贴密码管理器生成的唯一随机密码（至少24位，含大小写字母、数字和符号）：", show="*", parent=root)
        if first is None:
            raise ReleaseError("用户取消了私人密码初始化")
        second = simpledialog.askstring("确认私有密码", "请再次输入同一个密码：", show="*", parent=root)
        if first != second:
            raise ReleaseError("两次输入的密码不一致")
        if not strong_passphrase(first):
            raise ReleaseError("密码强度不足：至少24位，并同时包含大小写字母、数字和符号")
        if not messagebox.askyesno("确认高熵密码", "请确认：这是密码管理器生成、仅用于本网站且已安全保存的随机密码。", parent=root):
            raise ReleaseError("用户未确认使用密码管理器生成的唯一随机密码")
        protected = dpapi_protect(first.encode("utf-8"))
        payload = {"schema": 1, "kind": "lzheng_fitness_workbench_private_secret", "protection": "windows-dpapi-current-user", "high_entropy_acknowledged": True, "ciphertext": base64.b64encode(protected).decode("ascii")}
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_name("." + path.name + ".tmp")
        staging.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, path)
        messagebox.showinfo("初始化完成", "私人密码已保存到当前 Windows 用户的加密区。请牢记该密码，打开网站时需要输入。", parent=root)
    finally:
        root.destroy()


def load_secret(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        protected = base64.b64decode(payload["ciphertext"], validate=True)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise ReleaseError("私人发布密钥不存在或格式损坏；请先执行 --initialize-secret") from exc
    if payload.get("schema") != 1 or payload.get("kind") != "lzheng_fitness_workbench_private_secret" or payload.get("high_entropy_acknowledged") is not True:
        raise ReleaseError("私人发布密钥格式不受支持")
    try:
        value = dpapi_unprotect(protected).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError("私人发布密钥解码失败") from exc
    if not strong_passphrase(value):
        raise ReleaseError("私人发布密钥未达到当前强度要求")
    return value


def safe_rel(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        return None
    return rel.as_posix()


def validate_source(root: Path) -> dict[str, Any]:
    manifest_path = root / MANIFEST_NAME
    if not root.is_dir() or not manifest_path.is_file():
        raise ReleaseError("私人源发布目录不存在或缺少 release-manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("私人源发布 manifest 无法解析") from exc
    if (manifest.get("schema"), manifest.get("kind"), manifest.get("producer")) != (SOURCE_SCHEMA, SOURCE_KIND, SOURCE_PRODUCER):
        raise ReleaseError("只接受受管 schema-2 私人发布副本")
    if manifest.get("release_mode") != "private-portable" or manifest.get("contains_personal_data") is not True or manifest.get("required_access") != "private-authenticated":
        raise ReleaseError("源发布副本没有声明 private-portable 私人访问边界")
    allowed = [safe_rel(item) for item in manifest.get("allowed_files", [])]
    if any(item is None for item in allowed) or len(allowed) != len(set(allowed)):
        raise ReleaseError("私人源 manifest allowed_files 无效")
    actual = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    if set(allowed) != set(actual):
        raise ReleaseError("私人源发布树与 manifest allowed_files 不一致")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ReleaseError("私人源 manifest 缺少文件哈希")
    by_path = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    if set(by_path) != set(allowed) - {MANIFEST_NAME}:
        raise ReleaseError("私人源 manifest 文件哈希列表不完整")
    for rel, entry in by_path.items():
        path = actual[rel]
        if entry.get("sha256") != sha256_file(path) or entry.get("bytes") != path.stat().st_size:
            raise ReleaseError("私人源文件哈希不一致: " + rel)
    return manifest


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def inline_private_html(root: Path, manifest: dict[str, Any]) -> bytes:
    index = root / "index.html"
    html = index.read_text(encoding="utf-8-sig")
    for rel in manifest["allowed_files"]:
        if rel in {"index.html", MANIFEST_NAME}:
            continue
        references = tuple(dict.fromkeys((rel, quote(rel, safe="/"))))
        count = sum(html.count(reference) for reference in references)
        if count == 0:
            raise ReleaseError("私人源包含未被 index.html 引用的文件: " + rel)
        uri = data_uri(root / PurePosixPath(rel))
        for reference in references:
            html = html.replace(reference, uri)
    for rel in manifest["allowed_files"]:
        if rel not in {"index.html", MANIFEST_NAME}:
            references = (rel, quote(rel, safe="/"))
            if any(reference in html for reference in references):
                raise ReleaseError("私人单文件仍残留本地资源引用: " + rel)
    return html.encode("utf-8")


def derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def launcher_html(title: str = "个人健身工作台") -> str:
    title_json = json.dumps(title, ensure_ascii=False)
    return r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>__TITLE__ · 私人访问</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#090d16;color:#edf3ff;font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif}.card{width:min(92vw,420px);padding:32px;border:1px solid #26334d;border-radius:22px;background:rgba(18,26,43,.96);box-shadow:0 24px 80px #0008}h1{margin:0 0 10px;font-size:25px}p{color:#9fb0c9;line-height:1.65}label{display:block;margin:22px 0 8px}input,button{width:100%;height:48px;border-radius:12px;font-size:16px}input{padding:0 14px;color:#fff;background:#0b1220;border:1px solid #40506c}button{margin-top:14px;border:0;background:#2f68ff;color:#fff;font-weight:700;cursor:pointer}button:disabled{opacity:.6;cursor:wait}.status{min-height:24px;margin-top:14px;color:#ffb4a8}.hint{font-size:13px}iframe{position:fixed;inset:0;width:100%;height:100%;border:0;background:#fff}</style></head>
<body><main class="card"><h1>__TITLE__</h1><p>这是加密的私人工作台。密码只在本机浏览器中用于解密，不会发送到网站。</p><label for="password">私人访问密码</label><input id="password" type="password" autocomplete="current-password" minlength="16"><button id="open">解密并打开</button><div id="status" class="status" role="status"></div><p class="hint">忘记密码时，云端内容无法恢复；请回到已授权电脑重新发布。</p></main>
<script>
const te=new TextEncoder(),td=new TextDecoder();
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function openWorkbench(){
 const button=document.getElementById('open'),input=document.getElementById('password'),status=document.getElementById('status');
 if(input.value.length<16){status.textContent='密码至少需要16位。';return}
 button.disabled=true;status.textContent='正在校验和解密…';
 try{
  const response=await fetch('private-payload.json',{cache:'no-store'});if(!response.ok)throw new Error('PAYLOAD');
  const p=await response.json();if(p.schema!==1||p.kind!=='lzheng_fitness_workbench_encrypted_payload')throw new Error('FORMAT');
  const material=await crypto.subtle.importKey('raw',te.encode(input.value),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt:b64(p.salt),iterations:p.iterations},material,{name:'AES-GCM',length:256},false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(p.nonce),additionalData:te.encode(p.aad)},key,b64(p.ciphertext));
  input.value='';const frame=document.createElement('iframe');frame.setAttribute('title',__TITLE_JSON__);frame.srcdoc=td.decode(plain);document.body.replaceChildren(frame);
 }catch(error){status.textContent='密码错误，或发布内容已损坏。';button.disabled=false;input.focus()}
}
document.getElementById('open').addEventListener('click',openWorkbench);document.getElementById('password').addEventListener('keydown',event=>{if(event.key==='Enter')openWorkbench()});
</script></body></html>'''.replace("__TITLE__", title).replace("__TITLE_JSON__", title_json)


def tree_files(root: Path) -> list[dict[str, Any]]:
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix())]


def promote(staging: Path, output: Path) -> None:
    previous = output.with_name("." + output.name + ".previous")
    if previous.exists():
        raise ReleaseError("加密发布目录旁存在未处理的 previous 目录，拒绝覆盖")
    if output.exists():
        try:
            old = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseError("目标目录不是受管加密发布目录，拒绝覆盖") from exc
        if old.get("kind") != OUTPUT_KIND:
            raise ReleaseError("目标目录不是受管加密发布目录，拒绝覆盖")
        os.replace(output, previous)
    try:
        os.replace(staging, output)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if not output.exists() and previous.exists():
            os.replace(previous, output)
        raise


def build(source: Path, output: Path, secret_file: Path) -> dict[str, Any]:
    source = source.resolve()
    output = output.expanduser().absolute().resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ReleaseError("私人源目录与加密输出目录不得重叠")
    manifest = validate_source(source)
    passphrase = load_secret(secret_file)
    private_html = inline_private_html(source, manifest)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ciphertext = AESGCM(derive_key(passphrase, salt)).encrypt(nonce, private_html, AAD)
    # Immediate cryptographic round-trip: a release is never promoted on a
    # merely successful encrypt() call.
    if AESGCM(derive_key(passphrase, salt)).decrypt(nonce, ciphertext, AAD) != private_html:
        raise ReleaseError("加密发布回读校验失败")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".candidate-", dir=parent))
    try:
        payload = {"schema": 1, "kind": "lzheng_fitness_workbench_encrypted_payload", "crypto": "AES-256-GCM", "kdf": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS, "salt": base64.b64encode(salt).decode("ascii"), "nonce": base64.b64encode(nonce).decode("ascii"), "aad": AAD.decode("ascii"), "ciphertext": base64.b64encode(ciphertext).decode("ascii")}
        (staging / "index.html").write_text(launcher_html(), encoding="utf-8")
        (staging / PAYLOAD_NAME).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        source_files = tree_files(source)
        source_tree = sha256_bytes(json.dumps(source_files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        output_manifest = {"schema": OUTPUT_SCHEMA, "kind": OUTPUT_KIND, "producer": OUTPUT_PRODUCER, "producer_version": SCRIPT_VERSION, "release_mode": "private-encrypted", "contains_personal_data": True, "personal_data_encrypted": True, "required_access": "strong-passphrase", "entrypoint": "index.html", "allowed_files": ["index.html", PAYLOAD_NAME, MANIFEST_NAME], "source_release": {"mode": "private-portable", "manifest_sha256": sha256_file(source / MANIFEST_NAME), "tree_sha256": source_tree}, "crypto": {"name": "AES-256-GCM", "kdf": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS, "salt_bytes": 16, "nonce_bytes": 12}, "files": tree_files(staging)}
        (staging / MANIFEST_NAME).write_text(json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        public_text = (staging / "index.html").read_text(encoding="utf-8") + (staging / PAYLOAD_NAME).read_text(encoding="utf-8") + (staging / MANIFEST_NAME).read_text(encoding="utf-8")
        if any(marker.lower() in public_text.lower() for marker in PRIVATE_MARKERS):
            raise ReleaseError("加密发布明文文件仍包含私人路径或深链")
        promote(staging, output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"status": "PASS", "release_dir": str(output), "mode": "private-encrypted", "files": [entry["path"] for entry in tree_files(output)], "manifest_sha256": sha256_file(output / MANIFEST_NAME), "payload_sha256": sha256_file(output / PAYLOAD_NAME), "plaintext_bytes": len(private_html), "ciphertext_bytes": len(ciphertext), "secret_storage": "windows-dpapi-current-user"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a password-encrypted private workbench release")
    parser.add_argument("--private-release")
    parser.add_argument("--out")
    parser.add_argument("--secret-file", default=str(default_secret_file()))
    parser.add_argument("--receipt", help="可选的项目外非敏感加密发布回执")
    parser.add_argument("--initialize-secret", action="store_true")
    parser.add_argument("--rotate-secret", action="store_true")
    args = parser.parse_args(argv)
    secret_file = Path(args.secret_file).expanduser().absolute()
    receipt_path = Path(args.receipt).expanduser().absolute() if args.receipt else None
    result: dict[str, Any]
    try:
        if args.initialize_secret or args.rotate_secret:
            if args.private_release or args.out:
                raise ReleaseError("密钥初始化或轮换必须单独执行")
            if args.initialize_secret and args.rotate_secret:
                raise ReleaseError("--initialize-secret 与 --rotate-secret 不能同时使用")
            initialize_secret(secret_file, rotate=args.rotate_secret)
            result = {"status": "PASS", "secret_initialized": True, "secret_rotated": bool(args.rotate_secret), "protection": "windows-dpapi-current-user", "high_entropy_acknowledged": True}
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if not args.private_release or not args.out:
            raise ReleaseError("生成加密发布必须同时指定 --private-release 与 --out")
        result = build(Path(args.private_release), Path(args.out), secret_file)
        if receipt_path:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_payload = {"schema": 1, "kind": "lzheng_fitness_workbench_encrypted_release_receipt", "claims": {"formal_refreshed": False, "release_prepared": True, "deployed": False, "online_verified": False}, "result": result}
            staging = receipt_path.with_name("." + receipt_path.name + ".tmp")
            staging.write_text(json.dumps(receipt_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(staging, receipt_path)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ReleaseError, OSError, ValueError) as exc:
        result = {"status": "FAIL", "error": str(exc)}
        if receipt_path:
            try:
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                receipt_path.write_text(json.dumps({"schema": 1, "kind": "lzheng_fitness_workbench_encrypted_release_receipt", "claims": {"formal_refreshed": False, "release_prepared": False, "deployed": False, "online_verified": False}, "result": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError:
                pass
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
