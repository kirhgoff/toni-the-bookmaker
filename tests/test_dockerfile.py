import re
from pathlib import Path

DOCKERFILE = (Path(__file__).parent.parent / "Dockerfile").read_text()


def test_image_has_a_compiler_for_triton() -> None:
    apt_install = re.search(r"apt-get install[^\n]*(?:\\\n[^\n]*)*", DOCKERFILE).group(0)
    assert re.search(r"\bgcc\b", apt_install)


def test_image_exposes_the_compile_flag_off_by_default() -> None:
    assert re.search(r"TONI_OMNI_COMPILE=0", DOCKERFILE)
