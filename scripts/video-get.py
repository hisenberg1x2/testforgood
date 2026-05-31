#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import re
import urllib.parse
import random
import shutil
import time
from pathlib import Path

RANDOM_WORDS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta",
    "theta", "kappa", "lambda", "sigma", "omega", "nova",
    "star", "moon", "sun", "sky", "cloud", "river", "ocean", "mountain",
]
SPLIT_MB = 45
SPLIT_BYTES = SPLIT_MB * 1024 * 1024

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/tmp/yt_cookies.txt")
HAS_COOKIES = os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 10


def sanitize_name(name):
    return re.sub(r"-+", "-", name.replace(" ", "-").replace("\u3000", "-"))


def urlencode(s):
    return urllib.parse.quote(s, safe="")


def get_random_word():
    return f"{random.choice(RANDOM_WORDS)}_{random.randint(0, 9999)}"


def get_unique_folder(base_path, backup_dir, name):
    if not os.path.isdir(f"{base_path}/{name}") and not os.path.isdir(f"{backup_dir}/{name}"):
        return name
    suffix = get_random_word()
    while os.path.isdir(f"{base_path}/{name}_{suffix}") or os.path.isdir(f"{backup_dir}/{name}_{suffix}"):
        suffix = get_random_word()
    return f"{name}_{suffix}"


def normalize_youtube_url(url):
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
    if match:
        vid = match.group(1).split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def get_format(quality):
    # YouTube format IDs:
    #   137 = 1080p mp4 video,  248 = 1080p webm (VP9)
    #   136 = 720p  mp4 video,  247 = 720p  webm
    #   135 = 480p  mp4 video,  244 = 480p  webm
    #   140 = audio m4a,        251 = audio opus
    # We avoid [ext=mp4] on video stream because YouTube serves
    # 1080p+ mostly as VP9/webm. ffmpeg merges to mp4 at the end.
    formats = {
        "audio": "bestaudio/bestaudio*/best",
        "best":  "bv*+ba/b",
        "1080":  "137+140/248+251/137+bestaudio/248+bestaudio/bestvideo[height=1080]+bestaudio/bestvideo[height<=1080][height>720]+bestaudio/b",
        "720":   "136+140/247+251/136+bestaudio/247+bestaudio/bestvideo[height=720]+bestaudio/bestvideo[height<=720][height>480]+bestaudio/b",
        "480":   "135+140/244+251/135+bestaudio/244+bestaudio/bestvideo[height=480]+bestaudio/bestvideo[height<=480]+bestaudio/b",
    }
    return formats.get(quality, formats["best"])


def is_playlist(url):
    return "playlist?list=" in url or ("/playlist" in url and "list=" in url)


def playlist_flag(url):
    return ["--yes-playlist"] if is_playlist(url) else ["--no-playlist"]


def build_args(quality, tmp_dir, url):
    out_tmpl = (
        f"{tmp_dir}/%(playlist_index)s-%(title)s.%(ext)s"
        if is_playlist(url)
        else f"{tmp_dir}/%(title)s.%(ext)s"
    )
    args = [
        "--no-cache-dir",
        "--output", out_tmpl,
        "--no-part",
        "--retries", "10",
        "--fragment-retries", "10",
        "--no-check-certificates",
        "--concurrent-fragments", "4",
        "--buffer-size", "16K",
        "--http-chunk-size", "10M",
        "--progress", "--newline",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36",
    ]
    if quality == "audio":
        args += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        args += ["--merge-output-format", "mp4", "--format-sort", "res,vbr,abr"]
    return args


def download_video(url, tmp_dir, fmt, quality):
    # yt-dlp 2026+: only web-based clients support cookies.
    # android/ios silently drop cookies -> only images available.
    # Use web client + deno (solves n-challenge) for all downloads.
    cookie_args = ["--cookies", COOKIES_FILE] if HAS_COOKIES else []
    deno_args = ["--js-runtimes", "deno", "--remote-components", "ejs:github"]
    pl_flag = playlist_flag(url)
    base = build_args(quality, tmp_dir, url)

    strategies = [
        {
            "label": "web + deno + cookies",
            "cmd": (
                ["yt-dlp"] + cookie_args
                + ["--format", fmt] + base + pl_flag
                + ["--extractor-args", "youtube:player_client=web"]
                + deno_args + [url]
            ),
            "needs_cookie": True,
        },
        {
            "label": "web_embedded + deno + cookies",
            "cmd": (
                ["yt-dlp"] + cookie_args
                + ["--format", fmt] + base + pl_flag
                + ["--extractor-args", "youtube:player_client=web_embedded"]
                + deno_args + [url]
            ),
            "needs_cookie": True,
        },
        {
            "label": "default + deno + cookies",
            "cmd": (
                ["yt-dlp"] + cookie_args
                + ["--format", fmt] + base + pl_flag
                + deno_args + [url]
            ),
            "needs_cookie": True,
        },
        {
            "label": "web + deno (no cookies)",
            "cmd": (
                ["yt-dlp"]
                + ["--format", fmt] + base + pl_flag
                + ["--extractor-args", "youtube:player_client=web"]
                + deno_args + [url]
            ),
            "needs_cookie": False,
        },
        {
            "label": "default + deno (no cookies)",
            "cmd": (
                ["yt-dlp"]
                + ["--format", fmt] + base + pl_flag
                + deno_args + [url]
            ),
            "needs_cookie": False,
        },
    ]

    for s in strategies:
        if s["needs_cookie"] and not HAS_COOKIES:
            print(f"  skip [{s['label']}] - no cookies")
            continue
        print(f"\n>> Trying: {s['label']}")
        try:
            result = subprocess.run(s["cmd"], check=False)
            if result.returncode == 0:
                print(f"  OK: {s['label']}")
                return True
            print(f"  FAIL: {s['label']} (exit {result.returncode})")
        except Exception as exc:
            print(f"  ERROR: {s['label']}: {exc}")
        time.sleep(3)

    return False

def get_video_height(filepath):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", filepath],
            capture_output=True, text=True,
        )
        return int(result.stdout.strip())
    except Exception:
        return None


def create_readme(folder_path, filename, url, quality, parts_info, has_password, is_split):
    readme = f"# {filename}\n\n"
    if os.path.exists(f"{folder_path}/thumbnail.jpg"):
        readme += (
            '<div align="center">\n  <picture>\n'
            '    <img src="thumbnail.jpg" width="250" />\n'
            "  </picture>\n</div>\n\n<br>\n\n"
        )
    readme += "---\n\n## Video Information\n\n| Property | Value |\n|----------|-------|\n"
    readme += f"| **Video Name** | `{filename}` |\n"
    readme += f"| **Original Link** | [YouTube Video]({url}) |\n"
    readme += (
        f"| **Total Size** | **{parts_info['count']} "
        f"{'parts' if is_split else 'file'}** - **{parts_info['size_mb']} MB** |\n"
    )
    readme += f"| **Quality** | **{quality}** |\n"
    readme += "| **Status** | **Complete (100%)** |\n"
    readme += f"| **Password Protected** | **{'YES' if has_password else 'NO'}** |\n\n"
    readme += "---\n\n## Download Links\n\n"
    if is_split:
        readme += (
            f"> Download **all parts**, then open `{parts_info['main_zip']}` "
            "- the other parts are found automatically.\n\n"
        )
    readme += "| # | File | Link |\n|---|------|------|\n"
    for i, link in enumerate(parts_info["links"], 1):
        readme += f"| {i} | `{link['name']}` | [Download]({link['url']}) |\n"
    readme += "\n---\n\n## How to Extract\n\n"
    if has_password:
        readme += "| OS | Steps |\n|----|-------|\n"
        readme += f"| **Windows** | Right-click `{parts_info['main_zip']}` -> Extract Here -> enter password |\n"
        readme += "| **Mac** | Open with Keka -> enter password |\n"
        readme += f"| **Linux** | `unzip {parts_info['main_zip']}` -> enter password |\n"
        readme += f"| **Android** | Use ZArchiver -> tap `{parts_info['main_zip']}` -> enter password |\n"
    elif is_split:
        readme += "| OS | Steps |\n|----|-------|\n"
        readme += f"| **Windows** | Double-click `{parts_info['main_zip']}` |\n"
        readme += f"| **Mac** | Double-click `{parts_info['main_zip']}` |\n"
        readme += f"| **Linux** | `unzip {parts_info['main_zip']}` |\n"
        readme += f"| **Android** | Tap `{parts_info['main_zip']}` in ZArchiver |\n"
    else:
        readme += "Ready to use - no extraction needed!\n"
    readme += "\n---\n\n*This tool created by [avasam.ir](https://avasam.ir)*\n"
    with open(f"{folder_path}/README.md", "w", encoding="utf-8") as fh:
        fh.write(readme)


def process_video(url, quality, password, backup_dir, repo_owner, repo_name, branch, url_index):
    url = normalize_youtube_url(url)
    print(f"\n{'='*60}")
    print(f"Processing URL {url_index}: {url}")
    print(f"Quality: {quality} | Cookies: {'YES' if HAS_COOKIES else 'NO'}")
    print("=" * 60)

    tmp_dir = f"tmp_downloads_{url_index}"
    os.makedirs(tmp_dir, exist_ok=True)
    fmt = get_format(quality)

    if not download_video(url, tmp_dir, fmt, quality):
        print(f"\nFAIL: all strategies failed for: {url}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    if quality not in ("best", "audio"):
        for f in Path(tmp_dir).glob("*.mp4"):
            h = get_video_height(str(f))
            if h:
                print(f"  Video height: {h}p")

    for p in Path(tmp_dir).glob("*.part"):
        p.unlink()

    video_info = []
    for filepath in Path(tmp_dir).iterdir():
        if filepath.suffix in (".jpg", ".webp") or not filepath.is_file():
            continue

        size = filepath.stat().st_size
        filename_no_ext = sanitize_name(filepath.stem)
        ext = filepath.suffix[1:]
        final_folder = get_unique_folder("videos", backup_dir, filename_no_ext)
        folder_path = f"{backup_dir}/{final_folder}"
        os.makedirs(folder_path, exist_ok=True)

        thumbs = list(Path(tmp_dir).glob("*.jpg"))
        if thumbs:
            shutil.copy(thumbs[0], f"{folder_path}/thumbnail.jpg")

        folder_encoded = urlencode(final_folder)

        if size > SPLIT_BYTES:
            archive_base = f"{folder_path}/{final_folder}"
            if password:
                subprocess.run([
                    "7z", "a", "-tzip", f"-v{SPLIT_MB}m",
                    f"-p{password}", "-mx=0",
                    f"{archive_base}.zip", str(filepath),
                ])
            else:
                subprocess.run([
                    "zip", "-0", "-s", f"{SPLIT_MB}m",
                    f"{archive_base}.zip", str(filepath),
                ])

            parts = sorted(Path(folder_path).glob("*.z*"))
            total_size = sum(p.stat().st_size for p in parts)
            links = [
                {
                    "name": p.name,
                    "url": (
                        f"https://raw.githubusercontent.com/{repo_owner}/"
                        f"{repo_name}/{branch}/videos/{folder_encoded}/{urlencode(p.name)}"
                    ),
                }
                for p in parts
            ]
            create_readme(
                folder_path, filename_no_ext, url, quality,
                {
                    "count": len(parts),
                    "size_mb": f"{total_size / 1024 / 1024:.2f}",
                    "main_zip": f"{final_folder}.zip",
                    "links": links,
                },
                bool(password), True,
            )
        else:
            if password:
                subprocess.run([
                    "zip", "-0", "-P", password,
                    f"{folder_path}/{final_folder}.zip", str(filepath),
                ])
                file_enc = urlencode(f"{final_folder}.zip")
                links = [{
                    "name": f"{final_folder}.zip",
                    "url": (
                        f"https://raw.githubusercontent.com/{repo_owner}/"
                        f"{repo_name}/{branch}/videos/{folder_encoded}/{file_enc}"
                    ),
                }]
                create_readme(
                    folder_path, filename_no_ext, url, quality,
                    {
                        "count": 1,
                        "size_mb": f"{size / 1024 / 1024:.2f}",
                        "main_zip": f"{final_folder}.zip",
                        "links": links,
                    },
                    True, False,
                )
            else:
                shutil.copy(filepath, f"{folder_path}/{final_folder}.{ext}")
                file_enc = urlencode(f"{final_folder}.{ext}")
                links = [{
                    "name": f"{final_folder}.{ext}",
                    "url": (
                        f"https://raw.githubusercontent.com/{repo_owner}/"
                        f"{repo_name}/{branch}/videos/{folder_encoded}/{file_enc}"
                    ),
                }]
                create_readme(
                    folder_path, filename_no_ext, url, quality,
                    {
                        "count": 1,
                        "size_mb": f"{size / 1024 / 1024:.2f}",
                        "main_zip": None,
                        "links": links,
                    },
                    False, False,
                )

        video_info.append({"original": filename_no_ext, "folder": final_folder})

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return video_info


def download_subtitles(url, folder_path, folder_name, repo_owner, repo_name, branch):
    subtitle_dir = f"{folder_path}/subtitle"
    os.makedirs(subtitle_dir, exist_ok=True)
    out_tmpl = f"{subtitle_dir}/%(title)s"
    cookie_args = ["--cookies", COOKIES_FILE] if HAS_COOKIES else []

    common = [
        "--sub-format", "vtt/srt/best",
        "--convert-subs", "vtt",
        "--skip-download", "--no-playlist",
        "--no-check-certificates",
        "--output", out_tmpl,
    ]

    def try_sub(sub_flags):
        for client in ["web", "mweb", "android"]:
            cmd = (
                ["yt-dlp"] + cookie_args
                + ["--extractor-args", f"youtube:player_client={client}"]
                + sub_flags + common + [url]
            )
            subprocess.run(cmd, check=False)
            subs = (
                list(Path(subtitle_dir).glob("*.vtt"))
                + list(Path(subtitle_dir).glob("*.srt"))
            )
            if subs:
                return True
        return False

    try_sub(["--write-sub", "--sub-langs", "fa,en"])
    en_ok = bool(
        list(Path(subtitle_dir).glob("*.en.vtt"))
        + list(Path(subtitle_dir).glob("*.en.srt"))
    )
    fa_ok = bool(
        list(Path(subtitle_dir).glob("*.fa.vtt"))
        + list(Path(subtitle_dir).glob("*.fa.srt"))
    )
    if not en_ok or not fa_ok:
        try_sub(["--write-auto-sub", "--sub-langs", "en,fa"])

    subs = list(Path(subtitle_dir).iterdir())
    if not subs:
        shutil.rmtree(subtitle_dir, ignore_errors=True)
        return

    zip_path = f"{folder_path}/subtitle.zip"
    subprocess.run(["zip", "-j", zip_path] + [str(s) for s in subs], check=False)
    shutil.rmtree(subtitle_dir, ignore_errors=True)

    folder_enc = urlencode(folder_name)
    sub_link = (
        f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}"
        f"/{branch}/videos/{folder_enc}/subtitle.zip"
    )
    readme_path = f"{folder_path}/README.md"
    if os.path.exists(readme_path):
        with open(readme_path, "r") as fh:
            content = fh.read()
        sub_section = (
            "\n---\n\n## Subtitles\n\n"
            "| # | File | Link |\n|---|------|------|\n"
            f"| 1 | `subtitle.zip` | [Download]({sub_link}) |\n\n"
            "> Contains all available subtitle languages.\n"
        )
        marker = "## Download Link"
        content = (
            content.replace(marker, sub_section + "\n" + marker)
            if marker in content
            else content + sub_section
        )
        with open(readme_path, "w") as fh:
            fh.write(content)


def main():
    urls = os.environ.get("YT_URLS", "").split()
    quality = os.environ.get("YT_QUALITY", "best")
    password = os.environ.get("YT_PASSWORD", "")
    download_subs = os.environ.get("DOWNLOAD_SUBS", "false").lower() == "true"
    repo_owner = os.environ.get("REPO_OWNER_ENV", "")
    repo_name = os.environ.get("REPO_NAME_ENV", "")
    branch = os.environ.get("BRANCH_ENV", "")

    if not urls:
        print("ERROR: No URLs provided.")
        sys.exit(1)

    if not HAS_COOKIES:
        print("WARNING: YT_COOKIES secret is not set. Age-restricted videos will fail.")

    backup_dir = f"/tmp/video_backup_{os.getpid()}"
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    all_info = []
    for i, url in enumerate(urls, 1):
        info = process_video(
            url, quality, password,
            backup_dir, repo_owner, repo_name, branch, i,
        )
        if info:
            all_info.extend((v, url) for v in info)

    if download_subs:
        for info, url in all_info:
            folder_path = f"{backup_dir}/{info['folder']}"
            download_subtitles(
                url, folder_path, info["folder"],
                repo_owner, repo_name, branch,
            )

    with open("/tmp/backup_dir_path.txt", "w") as fh:
        fh.write(backup_dir)
    with open("/tmp/video_info.txt", "w") as fh:
        for info, _ in all_info:
            fh.write(f"{info['original']}|{info['folder']}\n")
    with open("/tmp/yt_urls.txt", "w") as fh:
        for url in urls:
            fh.write(url + "\n")
    with open("/tmp/env_vars.txt", "w") as fh:
        fh.write(f"REPO_OWNER_ENV={repo_owner}\n")
        fh.write(f"REPO_NAME_ENV={repo_name}\n")
        fh.write(f"BRANCH_ENV={branch}\n")

    print(f"\nDone: processed {len(all_info)} video(s).")


if __name__ == "__main__":
    main()
                                       
