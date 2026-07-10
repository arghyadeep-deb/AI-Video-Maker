import sys
from pathlib import Path

# Make `worker_agent` importable when pytest runs from worker-agent/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
