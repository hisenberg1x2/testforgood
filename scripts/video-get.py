#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import re
import urllib.parse
import random
import shutil
from pathlib import Path

# ==========================================
# ثابت‌ها
# ==========================================
RANDOM_WORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "theta",
                "kappa", "lambda", "sigma", "omega", "nova", "star", "moon",
                "sun", "sky", "cloud", "river", "ocean", "mountain"]
SPLIT_MB = 45
SPLIT_BYTES = SPLIT_MB * 1024 * 1024

# ==========================================
# توابع کمکی
# ==========================================
def sanitize_name(name):
    return re.sub(r'-+', '-', name.replace(' ', '-').replace('　', '-'))

def urlencode(s):
    return urllib.parse.quote(s, safe='')

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
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', url)
    if match:
        vid = match.group(1).split('?')[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return url

# ==========================================
# فرمت و آرگومان‌های yt-dlp
# ==========================================
def get_format(quality):
    formats = {
        "audio": "bestaudio/bestaudio*/best",
        "best": "bv*+ba/b",
        "2160": "bestvideo[height<=2160]+bestaudio/bestvideo[height<=2160]*+bestaudio*/bestvideo+bestaudio/best",
        "4k": "bestvideo[height<=2160]+bestaudio/bestvideo[height<=2160]*+bestaudio*/bestvideo+bestaudio/best",
        "1440": "bestvideo[height<=1440]+bestaudio/bestvideo[height<=1440]*+bestaudio*/bestvideo+bestaudio/best",
        "2k": "bestvideo[height<=1440]+bestaudio/bestvideo[height<=1440]*+bestaudio*/bestvideo+bestaudio/best",
        "1080": "bestvideo[height<=1080]+bestaudio/bestvideo[height<=1080]*+bestaudio*/bestvideo+bestaudio/best",
        "720": "bestvideo[height<=720]+bestaudio/bestvideo[height<=720]*+bestaudio*/bestvideo+bestaudio/best",
        "480": "bestvideo[height<=480]+bestaudio/bestvideo[height<=480]*+bestaudio*/bestvideo+bestaudio/best",
    }
    return formats.get(quality, formats["best"])

def get_common_args(quality, tmp_dir, cookies_file):
    """آرگومان‌های yt-dlp با Deno و remote components (حل n-challenge)"""
    base = [
        "--cookies", cookies_file,
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--no-cache-dir", "--output", f"{tmp_dir}/%(title)s.%(ext)s",
        "--no-part", "--no-playlist", "--retries", "10",
        "--fragment-retries", "10", "--no-check-certificates",
        "--concurrent-fragments", "8", "--buffer-size", "16K",
        "--http-chunk-size", "10M", "--progress", "--newline",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "--extractor-args", "youtube:player_client=web,android,android_vr",
        "--js-runtimes", "deno",
        "--remote-components", "ejs:github",
        "--compat-options", "no-keep-subs"
    ]
    if quality == "audio":
        return ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"] + base
    else:
        return ["--merge-output-format", "mp4"] + base

def download_video(url, tmp_dir, fmt, quality, cookies_file):
    """اجرای yt-dlp با کوکی و Deno"""
    common = get_common_args(quality, tmp_dir, cookies_file)
    cmd = ["yt-dlp", "--format", fmt] + common + [url]
    print(f"Downloading with cookies + Deno: {' '.join(cmd[:5])}...")
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False

def get_video_height(filepath):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=height', '-of', 'csv=p=0', filepath],
            capture_output=True, text=True
        )
        return int(result.stdout.strip())
    except:
        return None

# ==========================================
# ساخت README (بدون تغییر)
# ==========================================
def create_readme(folder_path, filename, url, quality, parts_info, has_password, is_split):
    readme = f"# {filename}\n\n"
    if os.path.exists(f"{folder_path}/thumbnail.jpg"):
        readme += '<div align="center">\n  <picture>\n    <img src="thumbnail.jpg" width="250" />\n  </picture>\n</div>\n\n<br>\n\n'
    readme += "---\n\n## Video Information\n\n| Property | Value |\n|----------|-------|\n"
    readme += f"| **Video Name** | `{filename}` |\n"
    readme += f"| **Original Link** | [YouTube Video]({url}) |\n"
    readme += f"| **Total Size** | **{parts_info['count']} {'parts' if is_split else 'file'}** - **{parts_info['size_mb']} MB** |\n"
    readme += f"| **Quality** | **{quality}** |\n"
    readme += "| **Status** | **Complete (100%)** |\n"
    readme += f"| **Password Protected** | **{'YES' if has_password else 'NO'}** |\n\n"
    readme += "---\n\n## Download Links\n\n"
    if is_split:
        readme += f"> Download **all parts**, then open `{parts_info['main_zip']}` — the other parts are found automatically.\n\n"
    readme += "| # | File | Link |\n|---|------|------|\n"
    for i, link in enumerate(parts_info['links'], 1):
        readme += f"| {i} | `{link['name']}` | [Download]({link['url']}) |\n"
    readme += "\n---\n\n## How to Extract\n\n"
    if has_password:
        readme += "| OS | Steps |\n|----|-------|\n"
        readme += f"| **Windows** | Right-click `{parts_info['main_zip']}` → *Extract Here* (needs 7-Zip or WinRAR) → enter password |\n"
        readme += "| **Mac** | Open with Keka → enter password |\n"
        readme += f"| **Linux** | `unzip {parts_info['main_zip']}` or right-click → Extract → enter password |\n"
        readme += f"| **Android** | Use ZArchiver → tap `{parts_info['main_zip']}` → enter password |\n"
    elif is_split:
        readme += "| OS | Steps |\n|----|-------|\n"
        readme += f"| **Windows** | Double-click `{parts_info['main_zip']}` — opens in Explorer, WinRAR, or 7-Zip |\n"
        readme += f"| **Mac** | Double-click `{parts_info['main_zip']}` — extracts with Archive Utility |\n"
        readme += f"| **Linux** | `unzip {parts_info['main_zip']}` or right-click → Extract Here |\n"
        readme += f"| **Android** | Tap `{parts_info['main_zip']}` in file manager or use ZArchiver |\n"
    else:
        readme += "Ready to use — no extraction needed!\n"
    readme += "\n---\n\n*This tool created by [avasam.ir](https://avasam.ir)*\n"
    with open(f"{folder_path}/README.md", 'w', encoding='utf-8') as f:
        f.write(readme)

# ==========================================
# پردازش ویدیو (تقسیم، رمز، README)
# ==========================================
def process_video(url, quality, password, backup_dir, repo_owner, repo_name, branch, url_index, cookies_file):
    url = normalize_youtube_url(url)
    print(f"Processing URL {url_index}: {url}")
    tmp_dir = f"tmp_downloads_{url_index}"
    os.makedirs(tmp_dir, exist_ok=True)
    fmt = get_format(quality)

    success = download_video(url, tmp_dir, fmt, quality, cookies_file)
    if not success:
        print(f"Download failed for URL: {url}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    # بررسی کیفیت واقعی
    if quality not in ["best", "audio"]:
        for f in Path(tmp_dir).glob("*.mp4"):
            h = get_video_height(str(f))
            target = int(quality)
            if h and h < target - 150:
                print(f"Downloaded {h}p instead of {quality}p — rejecting")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None

    # پاک کردن فایل‌های .part
    for p in Path(tmp_dir).glob("*.part"):
        p.unlink()

    video_info = []
    for filepath in Path(tmp_dir).iterdir():
        if filepath.suffix in ['.jpg', '.webp']:
            continue
        if not filepath.is_file():
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
                subprocess.run(["7z", "a", "-tzip", f"-v{SPLIT_MB}m", f"-p{password}", "-mx=0",
                                f"{archive_base}.zip", str(filepath)])
            else:
                subprocess.run(["zip", "-0", "-s", f"{SPLIT_MB}m",
                                f"{archive_base}.zip", str(filepath)])

            parts = sorted(Path(folder_path).glob("*.z*"))
            total_size = sum(p.stat().st_size for p in parts)
            links = []
            for p in parts:
                pname = p.name
                penc = urlencode(pname)
                links.append({'name': pname, 'url': f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/videos/{folder_encoded}/{penc}"})

            create_readme(folder_path, filename_no_ext, url, quality, {
                'count': len(parts), 'size_mb': f"{total_size/1024/1024:.2f}",
                'main_zip': f"{final_folder}.zip", 'links': links
            }, bool(password), True)
        else:
            if password:
                subprocess.run(["zip", "-0", "-P", password, f"{folder_path}/{final_folder}.zip", str(filepath)])
                file_enc = urlencode(f"{final_folder}.zip")
                links = [{'name': f"{final_folder}.zip", 'url': f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/videos/{folder_encoded}/{file_enc}"}]
                create_readme(folder_path, filename_no_ext, url, quality, {
                    'count': 1, 'size_mb': f"{size/1024/1024:.2f}",
                    'main_zip': f"{final_folder}.zip", 'links': links
                }, True, False)
            else:
                shutil.copy(filepath, f"{folder_path}/{final_folder}.{ext}")
                file_enc = urlencode(f"{final_folder}.{ext}")
                links = [{'name': f"{final_folder}.{ext}", 'url': f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/videos/{folder_encoded}/{file_enc}"}]
                create_readme(folder_path, filename_no_ext, url, quality, {
                    'count': 1, 'size_mb': f"{size/1024/1024:.2f}",
                    'main_zip': None, 'links': links
                }, False, False)

        video_info.append({'original': filename_no_ext, 'folder': final_folder})

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return video_info

# ==========================================
# زیرنویس (با Deno)
# ==========================================
def download_subtitles(url, folder_path, folder_name, repo_owner, repo_name, branch, cookies_file):
    subtitle_dir = f"{folder_path}/subtitle"
    os.makedirs(subtitle_dir, exist_ok=True)
    out_tmpl = f"{subtitle_dir}/%(title)s"

    cmd_all = [
        "yt-dlp", "--cookies", cookies_file,
        "--write-sub", "--sub-langs", "fa,en",
        "--sub-format", "vtt/srt/best", "--convert-subs", "vtt",
        "--skip-download", "--no-playlist", "--no-check-certificates",
        "--output", out_tmpl,
        "--extractor-args", "youtube:player_client=web,android,android_vr",
        "--js-runtimes", "deno", "--remote-components", "ejs:github",
        url
    ]
    subprocess.run(cmd_all, check=False)

    en_count = len(list(Path(subtitle_dir).glob("*.en.vtt")) + list(Path(subtitle_dir).glob("*.en.srt")))
    fa_count = len(list(Path(subtitle_dir).glob("*.fa.vtt")) + list(Path(subtitle_dir).glob("*.fa.srt")))
    if en_count == 0 or fa_count == 0:
        cmd_auto = [
            "yt-dlp", "--cookies", cookies_file,
            "--write-auto-sub", "--sub-langs", "en,fa",
            "--sub-format", "vtt/srt/best", "--convert-subs", "vtt",
            "--skip-download", "--no-playlist", "--no-check-certificates",
            "--output", out_tmpl,
            "--extractor-args", "youtube:player_client=web,android,android_vr",
            "--js-runtimes", "deno", "--remote-components", "ejs:github",
            url
        ]
        subprocess.run(cmd_auto, check=False)

    subs = list(Path(subtitle_dir).iterdir())
    if not subs:
        shutil.rmtree(subtitle_dir, ignore_errors=True)
        return

    zip_path = f"{folder_path}/subtitle.zip"
    subprocess.run(["zip", "-j", zip_path] + [str(s) for s in subs], check=False)
    shutil.rmtree(subtitle_dir, ignore_errors=True)

    folder_enc = urlencode(folder_name)
    sub_link = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/videos/{folder_enc}/subtitle.zip"
    readme_path = f"{folder_path}/README.md"
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        sub_section = f"\n---\n\n## Subtitles\n\n| # | File | Link |\n|---|------|------|\n| 1 | `subtitle.zip` | [Download]({sub_link}) |\n\n> Contains all available subtitle languages.\n"
        if "## Download Links" in content:
            content = content.replace("## Download Links", sub_section + "\n## Download Links")
        else:
            content += sub_section
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(content)

# ==========================================
# تابع اصلی
# ==========================================
def main():
    urls = os.environ.get('YT_URLS', '').split()
    quality = os.environ.get('YT_QUALITY', 'best')
    password = os.environ.get('YT_PASSWORD', '')
    download_subs = os.environ.get('DOWNLOAD_SUBS', 'false').lower() == 'true'
    repo_owner = os.environ.get('REPO_OWNER_ENV', '')
    repo_name = os.environ.get('REPO_NAME_ENV', '')
    branch = os.environ.get('BRANCH_ENV', '')
    cookies_str = os.environ.get('YT_COOKIES', '')

    if not cookies_str:
        print("ERROR: YT_COOKIES environment variable is empty. Please set it in GitHub Secrets.")
        sys.exit(1)

    cookies_file = "/tmp/youtube_cookies.txt"
    with open(cookies_file, 'w') as f:
        f.write(cookies_str)

    backup_dir = f"/tmp/video_backup_{os.getpid()}"
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    all_info = []
    for i, url in enumerate(urls, 1):
        info = process_video(url, quality, password, backup_dir, repo_owner, repo_name, branch, i, cookies_file)
        if info:
            all_info.extend([(v, url) for v in info])

    if download_subs:
        for info, url in all_info:
            folder_path = f"{backup_dir}/{info['folder']}"
            download_subtitles(url, folder_path, info['folder'], repo_owner, repo_name, branch, cookies_file)

    os.remove(cookies_file)

    with open('/tmp/backup_dir_path.txt', 'w') as f:
        f.write(backup_dir)
    with open('/tmp/video_info.txt', 'w') as f:
        for info, _ in all_info:
            f.write(f"{info['original']}|{info['folder']}\n")
    with open('/tmp/yt_urls.txt', 'w') as f:
        for url in urls:
            f.write(url + '\n')
    with open('/tmp/env_vars.txt', 'w') as f:
        f.write(f"REPO_OWNER_ENV={repo_owner}\n")
        f.write(f"REPO_NAME_ENV={repo_name}\n")
        f.write(f"BRANCH_ENV={branch}\n")

    print(f"Processed {len(all_info)} videos")

if __name__ == "__main__":
    main()
