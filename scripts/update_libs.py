#!/usr/bin/env python3
"""Atualiza as bibliotecas externas do ffmpeg-builder (libraries.json) para a versão estável mais nova.

Para cada biblioteca: lista as tags do repositório oficial (git ls-remote), ordena, e escolhe a mais
nova cujo download realmente existe (e, nas bibliotecas autotools, cujo tarball traz o `configure`).
Se nada validar, mantém a versão que já estava no builder.

Uso: update_libs.py libraries.json [resumo.md]
"""
import json
import os
import re
import subprocess
import sys
import tempfile

# repo: onde listar as tags | tag: regex com 1 grupo (a versão) | transform: tag->versão
# autotools: o tarball precisa conter ./configure | url: download explícito ({v} = versão) | folder: idem
LIBS = {
    "libaom":       dict(repo="https://aomedia.googlesource.com/aom", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libass":       dict(repo="https://github.com/libass/libass", tag=r"^(\d+\.\d+\.\d+)$", autotools=True),
    # libbluray: o autoreconf do builder falha no tarball da 1.5.x; fica na 1.3.4, que o builder foi escrito para usar
    "libbluray":    dict(repo=None),
    "libdav1d":     dict(repo="https://code.videolan.org/videolan/dav1d", tag=r"^(\d+\.\d+\.\d+)$"),
    "libfdk-aac":   dict(repo="https://github.com/mstorsjo/fdk-aac", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libfontconfig": dict(repo="https://gitlab.freedesktop.org/fontconfig/fontconfig", tag=r"^(\d+\.\d+\.\d+)$", autotools=True),
    "libfreetype":  dict(repo="https://github.com/freetype/freetype", tag=r"^VER-(\d+-\d+-\d+)$",
                         transform=lambda t: t.replace("-", "."), autotools=True),
    "libfribidi":   dict(repo="https://github.com/fribidi/fribidi", tag=r"^v(\d+\.\d+\.\d+)$", autotools=True),
    "libgme":       dict(repo="https://github.com/libgme/game-music-emu", tag=r"^(\d+\.\d+\.\d+)$",
                         url="https://github.com/libgme/game-music-emu/releases/download/{v}/game-music-emu-{v}.tar.xz",
                         file="game-music-emu-{v}.tar.xz", folder="game-music-emu-{v}/build"),
    "libkvazaar":   dict(repo="https://github.com/ultravideo/kvazaar", tag=r"^v(\d+\.\d+\.\d+)$", autotools=True),
    "libopencore":  dict(repo=None),  # 0.1.6 continua sendo a última
    "libopenh264":  dict(repo="https://github.com/cisco/openh264", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libopenjpeg":  dict(repo="https://github.com/uclouvain/openjpeg", tag=r"^v(2\.\d+\.\d+)$"),
    "libopus":      dict(repo="https://github.com/xiph/opus", tag=r"^v(\d+\.\d+(?:\.\d+)?)$", autotools=True),
    "libshine":     dict(repo="https://github.com/toots/shine", tag=r"^(\d+\.\d+\.\d+)$"),
    "libsoxr":      dict(repo="https://github.com/chirlu/soxr", tag=r"^(\d+\.\d+\.\d+)$"),
    "libsrt":       dict(repo="https://github.com/Haivision/srt", tag=r"^v(1\.\d+\.\d+)$"),
    "libsvtav1":    dict(repo="https://gitlab.com/AOMediaCodec/SVT-AV1", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libtheora":    dict(repo="https://github.com/xiph/theora", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libvidstab":   dict(repo="https://github.com/georgmartius/vid.stab", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libvmaf":      dict(repo="https://github.com/Netflix/vmaf", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libvorbis":    dict(repo="https://github.com/xiph/vorbis", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libvpx":       dict(repo="https://github.com/webmproject/libvpx", tag=r"^v(\d+\.\d+\.\d+)$"),
    "libx265":      dict(repo="https://bitbucket.org/multicoreware/x265_git", tag=r"^(\d+\.\d+(?:\.\d+)?)$"),
    "libxvid":      dict(repo=None),  # 1.3.7 continua sendo a última
    "libzimg":      dict(repo="https://github.com/sekrit-twc/zimg", tag=r"^release-(\d+\.\d+(?:\.\d+)?)$"),
    # OpenSSL: fica na série 3.x (a 4.x é um salto de API grande demais para um build estático)
    "openssl":      dict(repo="https://github.com/openssl/openssl", tag=r"^openssl-(3\.\d+\.\d+)$",
                         url="https://github.com/openssl/openssl/releases/download/openssl-{v}/openssl-{v}.tar.gz",
                         file="openssl-{v}.tar.gz", folder="openssl-{v}"),
    "zlib":         dict(repo="https://github.com/madler/zlib", tag=r"^v(\d+\.\d+(?:\.\d+)*)$"),
}
# libx264 (branch stable) e libmp3lame (fork custom, master) não têm versão fixa.

VER = re.compile(r"\d+(?:\.\d+)+[a-z]?")


def vkey(v):
    return [int(x) for x in re.findall(r"\d+", v)]


def tags(repo, rx, transform):
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs", repo],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        print(f"  ! ls-remote falhou em {repo}: {out.stderr.strip()[:120]}")
        return []
    found = set()
    for line in out.stdout.splitlines():
        t = line.split("refs/tags/")[-1].strip()
        m = re.match(rx, t)
        if m:
            found.add(transform(m.group(1)) if transform else m.group(1))
    return sorted(found, key=vkey, reverse=True)


def exists(url):
    return subprocess.run(["curl", "-fsSL", "-r", "0-99", "--retry", "4", "--retry-all-errors", "--retry-delay", "3", "-o", os.devnull, url],
                          capture_output=True).returncode == 0


def has_configure(url):
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "a")
        if subprocess.run(["curl", "-fsSL", "--retry", "4", "--retry-all-errors", "--retry-delay", "3", "-o", f, url]).returncode != 0:
            return False
        names = subprocess.run(["tar", "-tf", f], capture_output=True, text=True).stdout.splitlines()
        return any(re.fullmatch(r"(\./)?[^/]+/configure", n) for n in names)


def main():
    path = sys.argv[1]
    summary = sys.argv[2] if len(sys.argv) > 2 else None
    data = json.load(open(path))
    rows = []
    for name, cfg in LIBS.items():
        entry = data.get(name)
        if not entry:
            continue
        url_old = entry["download_params"][0]
        m = VER.search(url_old)
        old = m.group(0) if m else "?"
        print(f"{name}: {old}")
        if not cfg.get("repo"):
            rows.append((name, old, old, "fixada" if name == "libbluray" else "já é a última"))
            continue
        cands = tags(cfg["repo"], cfg["tag"], cfg.get("transform"))
        chosen = None
        for v in cands[:5]:
            if vkey(v) < vkey(old.rstrip("abcdefghijklmnopqrstuvwxyz")) and old != "?":
                break  # nunca regredir
            if "url" in cfg:
                new_entry = dict(entry)
                new_entry["download_params"] = [cfg["url"].format(v=v), cfg["file"].format(v=v)]
                new_entry["folder_name"] = cfg["folder"].format(v=v)
            else:
                text = json.dumps(entry).replace(old, v)
                new_entry = json.loads(text)
            u = new_entry["download_params"][0]
            if not exists(u):
                print(f"  - {v}: download indisponível ({u})")
                continue
            if cfg.get("autotools") and not has_configure(u):
                print(f"  - {v}: tarball sem ./configure, pulando")
                continue
            chosen = (v, new_entry)
            break
        if chosen is None:
            rows.append((name, old, old, "mantida (nada novo validou)"))
            continue
        v, new_entry = chosen
        data[name] = new_entry
        rows.append((name, old, v, "atualizada" if v != old else "já é a última"))
        print(f"  -> {v}")

    json.dump(data, open(path, "w"), indent=4)
    table = "| Biblioteca | Antes | Agora | Status |\n|---|---|---|---|\n" + \
            "\n".join(f"| {n} | {o} | {v} | {s} |" for n, o, v, s in rows) + "\n"
    print("\n" + table)
    if summary:
        open(summary, "w").write(table)


if __name__ == "__main__":
    main()
