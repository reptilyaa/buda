import subprocess

for path in ["ffmpeg", "/home/container/installed_packages/ffmpeg", "/home/container/installed_packages/bin/ffmpeg"]:
    try:
        result = subprocess.run([path, "-version"], capture_output=True, text=True, check=True)
        print(f"FFmpeg найден по пути: {path}")
        print(result.stdout)
    except Exception as e:
        print(f"Не найден по пути {path}: {e}")
