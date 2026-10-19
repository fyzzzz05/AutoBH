"""Build the Product Design frontend and include it in the Python package."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
subprocess.run(["npm", "run", "build"], cwd=root / "gui", check=True)
source = root / "gui" / "dist" / "client"
destination = root / "src" / "autobh" / "web"
if destination.exists():
    shutil.rmtree(destination)
shutil.copytree(source, destination)
print(f"GUI packaged: {destination}")
