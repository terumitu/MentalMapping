"""プロジェクトルートを sys.path に追加して modules パッケージを import 可能にする。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
