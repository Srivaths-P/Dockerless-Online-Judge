import os
import requests
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
VENDOR_DIR = STATIC_DIR / "vendor"

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
    {
        "url": "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
        "path": "mathjax/tex-mml-chtml.js"
    }
]


def download_assets():
    print(f"Vendor directory: {VENDOR_DIR}\n")
    if not VENDOR_DIR.exists():
        print("Creating vendor directory...")
        VENDOR_DIR.mkdir(parents=True)

    session = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0'}

    for asset in ASSETS:
        url = asset['url']
        local_path = VENDOR_DIR / asset['path']

        local_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Downloading {url}...")
        try:
            response = session.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                f.write(response.content)

            print(f" -> Saved to {local_path}")
        except requests.exceptions.RequestException as e:
            print(f" [ERROR] Failed to download {url}: {e}")

        time.sleep(0.1)

    print("\n✅ All assets downloaded successfully.")


if __name__ == "__main__":
    download_assets()
