from pathlib import Path


def test_director_console_output_is_cp949_encodable():
    source = Path(__file__).resolve().parents[1] / "tools" / "vn_director_console.py"
    source.read_text(encoding="utf-8").encode("cp949")
