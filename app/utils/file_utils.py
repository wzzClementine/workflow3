from pathlib import Path


def ensure_dir(path: Path | str) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_runtime_dirs(data_root: Path | str) -> dict[str, Path]:
    data_root = ensure_dir(data_root)

    dirs = {
        "data_root": data_root,
        "logs": ensure_dir(data_root / "logs"),
        "temp": ensure_dir(data_root / "temp"),
        "papers": ensure_dir(data_root / "papers"),
    }
    return dirs