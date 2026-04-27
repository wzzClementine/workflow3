from PIL import Image
from pathlib import Path

p = Path("runtime_data/tasks/task_b6decb79fbbe/rendered_pages/blank/page_1.png")
img = Image.open(p)
print(img.size, p.stat().st_size / 1024 / 1024)