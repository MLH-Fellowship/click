import os
import shutil
import tempfile

import pytest

from click.testing import CliRunner


@pytest.fixture(scope="function")
def runner(request):
    return CliRunner()


def check_symlink_impl():
    TEMP_DIR = os.path.join(tempfile.gettempdir())
    os.makedirs(os.path.join(TEMP_DIR, "click"), exist_ok=True)
    test_pth = os.path.join(TEMP_DIR, "click", "test_sym_impl")
    sym_pth = os.path.join(TEMP_DIR, "click", "sym_test_symlink_impl")
    with open(test_pth, "w"):
        pass
    rv = True
    try:
        os.symlink(test_pth, sym_pth)
    except NotImplementedError:
        rv = False
    finally:
        shutil.rmtree(os.path.join(TEMP_DIR, "click"))
    return rv
