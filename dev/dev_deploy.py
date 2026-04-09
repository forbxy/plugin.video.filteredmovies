# Dev Deploy Script - Deploy to local Kodi addon directory
# Usage: python dev_deploy.py

import os
import shutil
import fnmatch

DEV_REMOTE = True

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEV_REMOTE:
    TARGET_DIR = r"F:\storage\.kodi\addons\plugin.video.filteredmovies"
else:
    TARGET_DIR = os.path.join(os.environ.get('APPDATA', ''), 'Kodi', 'addons', 'plugin.video.filteredmovies')

EXCLUDE_DIRS = {'.git', '.github', '.vscode', '.idea', '__pycache__', 'dist', 'test', 'dev'}
EXCLUDE_FILES = {'*.pyc', '.gitignore', '.DS_Store', 'checklist.md'}


def should_exclude_file(name):
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILES)


def remove_readonly(func, path, excinfo):
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)

def deploy():
    print(f"\033[32mStarting deployment to dev environment...\033[0m")
    print(f"Source Dir: {SOURCE_DIR}")
    print(f"Target Dir: {TARGET_DIR}")
    print()

    # Clean target
    if os.path.exists(TARGET_DIR):
        print(f"\033[33mCleaning target directory with system command...\033[0m")
        import subprocess
        subprocess.run(f'cmd /c rmdir /s /q "{TARGET_DIR}"', shell=True)
    os.makedirs(TARGET_DIR, exist_ok=True)

    # Copy files
    print(f"\033[33mCopying files...\033[0m")
    for root, dirs, files in os.walk(SOURCE_DIR):
        # Exclude directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        rel_root = os.path.relpath(root, SOURCE_DIR)

        for f in files:
            if should_exclude_file(f):
                continue
            rel_path = os.path.join(rel_root, f) if rel_root != '.' else f
            src = os.path.join(root, f)
            dst = os.path.join(TARGET_DIR, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  Copy: {rel_path}")

    print()
    print(f"\033[32mDeployment Complete!\033[0m")
    print(f"Target Dir: {TARGET_DIR}")
    print()
    print(f"\033[36mTip: Restart Kodi or Reload Addons to see changes.\033[0m")


if __name__ == '__main__':
    deploy()
