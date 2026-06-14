import io
import tarfile

import pytest

from tegra_button.flash import ArtifactError, TegraflashArtifact


def _make_artifact(tmp_path, members):
    path = tmp_path / "img.tegraflash-tar"
    with tarfile.open(path, "w") as tf:
        for name in members:
            data = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def test_validate_ok(tmp_path):
    a = TegraflashArtifact(_make_artifact(tmp_path, ["initrd-flash", "other.bin"]))
    a.validate()  # must not raise


def test_validate_missing_marker(tmp_path):
    a = TegraflashArtifact(_make_artifact(tmp_path, ["random.bin"]))
    with pytest.raises(ArtifactError):
        a.validate()


def test_missing_artifact():
    with pytest.raises(ArtifactError):
        TegraflashArtifact("/no/such/file")


def test_sha256_and_extract(tmp_path):
    a = TegraflashArtifact(_make_artifact(tmp_path, ["initrd-flash"]))
    assert len(a.sha256()) == 64
    a.extract(tmp_path / "out")
    assert (tmp_path / "out" / "initrd-flash").is_file()
