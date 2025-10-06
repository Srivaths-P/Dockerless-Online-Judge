import os
import requests
from pathlib import Path
import time
import shutil
import zipfile
import io

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
VENDOR_DIR = STATIC_DIR / "vendor"

# URL for the complete MathJax v3 distribution zip
MATHJAX_URL = "https://github.com/mathjax/MathJax/archive/refs/tags/3.2.2.zip"
MATHJAX_DIR_NAME = "MathJax-3.2.2"  # The directory name inside the zip

ASSETS = [
    {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
        "path": "bootstrap/css/bootstrap.min.css"
    },
    {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
        "path": "bootstrap/js/bootstrap.bundle.min.js"
    },
    {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        "path": "bootstrap-icons/font/bootstrap-icons.min.css"
    },
    {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2",
        "path": "bootstrap-icons/font/fonts/bootstrap-icons.woff2"
    },
    {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff",
        "path": "bootstrap-icons/font/fonts/bootstrap-icons.woff"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/codemirror.min.css",
        "path": "codemirror/codemirror.min.css"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/codemirror.min.js",
        "path": "codemirror/codemirror.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/theme/material-darker.min.css",
        "path": "codemirror/theme/material-darker.min.css"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/mode/python/python.min.js",
        "path": "codemirror/mode/python/python.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/mode/clike/clike.min.js",
        "path": "codemirror/mode/clike/clike.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/display/fullscreen.css",
        "path": "codemirror/addon/display/fullscreen.css"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/display/fullscreen.min.js",
        "path": "codemirror/addon/display/fullscreen.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/edit/matchbrackets.min.js",
        "path": "codemirror/addon/edit/matchbrackets.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/edit/closebrackets.min.js",
        "path": "codemirror/addon/edit/closebrackets.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/selection/active-line.min.js",
        "path": "codemirror/addon/selection/active-line.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/comment/comment.min.js",
        "path": "codemirror/addon/comment/comment.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/foldcode.min.js",
        "path": "codemirror/addon/fold/foldcode.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/foldgutter.css",
        "path": "codemirror/addon/fold/foldgutter.css"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/foldgutter.min.js",
        "path": "codemirror/addon/fold/foldgutter.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/brace-fold.min.js",
        "path": "codemirror/addon/fold/brace-fold.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/comment-fold.min.js",
        "path": "codemirror/addon/fold/comment-fold.min.js"
    },
    {
        "url": "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.15/addon/fold/indent-fold.min.js",
        "path": "codemirror/addon/fold/indent-fold.min.js"
    },
]


def download_assets():
    print(f"Vendor directory: {VENDOR_DIR}\n")
    if not VENDOR_DIR.exists():
        print("Creating vendor directory...")
        VENDOR_DIR.mkdir(parents=True)

    session = requests.Session()
    headers = {'User-Agent': 'DOJ Asset Downloader'}

    # --- Standard Asset Download ---
    for asset in ASSETS:
        url = asset['url']
        local_path = VENDOR_DIR / asset['path']

        if local_path.exists():
            print(f"Skipping {local_path} (already exists).")
            continue

        local_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Downloading {url}...")
        try:
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                f.write(response.content)

            print(f" -> Saved to {local_path}")
        except requests.exceptions.RequestException as e:
            print(f" [ERROR] Failed to download {url}: {e}")
        time.sleep(0.1)

    # --- Special Handling for MathJax ---
    mathjax_target_dir = VENDOR_DIR / "mathjax"
    if mathjax_target_dir.exists() and any(mathjax_target_dir.iterdir()):
        print(f"\nSkipping MathJax (directory {mathjax_target_dir} already exists and is not empty).")
    else:
        print(f"\n--- Handling MathJax Distribution ---")
        print(f"Downloading {MATHJAX_URL}...")
        try:
            response = session.get(MATHJAX_URL, headers=headers, timeout=120, stream=True)
            response.raise_for_status()

            zip_file = zipfile.ZipFile(io.BytesIO(response.content))

            print("Extracting MathJax...")
            # Clean up target directory before extraction
            if mathjax_target_dir.exists():
                shutil.rmtree(mathjax_target_dir)

            # We only need the 'es5' directory from the distribution
            source_es5_path = f"{MATHJAX_DIR_NAME}/es5"
            for member in zip_file.infolist():
                if member.filename.startswith(source_es5_path) and not member.is_dir():
                    # Calculate the destination path
                    relative_path = os.path.relpath(member.filename, source_es5_path)
                    target_path = mathjax_target_dir / relative_path

                    # Create parent directories if they don't exist
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract the file
                    with zip_file.open(member) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

            print(f" -> MathJax successfully extracted to {mathjax_target_dir}")

        except requests.exceptions.RequestException as e:
            print(f" [ERROR] Failed to download MathJax: {e}")
        except zipfile.BadZipFile:
            print(f" [ERROR] Failed to extract MathJax: Downloaded file is not a valid zip archive.")
        except Exception as e:
            print(f" [ERROR] An unexpected error occurred while handling MathJax: {e}")

    print("\n✅ Asset download process complete.")


if __name__ == "__main__":
    download_assets()
