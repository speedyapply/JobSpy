from datetime import datetime
from pathlib import Path

_format = "%Y-%m-%d_%H-%M-%S"
RUN_ID = datetime.now().strftime(_format)
DATA_DIR = Path("./data")
RUN_DIR = DATA_DIR.joinpath(RUN_ID)
RUN_DIR.mkdir(parents=True, exist_ok=True)
