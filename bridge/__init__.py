"""DeviceBridge: original Windows transfer utility."""
import sys
from pathlib import Path

vendor = Path(__file__).resolve().parents[1] / 'vendor'
if vendor.is_dir():
    sys.path.insert(0, str(vendor))
