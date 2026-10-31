"""Hardware-free integration test for static firmware fingerprints."""

import hashlib
import subprocess
from pathlib import Path

import yaml


DISCO_SCRIPT = Path(__file__).parent.parent.parent.parent / "disco"


def test_fingerprint_static_match(tmp_path: Path):
    """The CLI accepts a matching repository-independent fingerprint."""
    firmware = tmp_path / "firmware.bin"
    data = b"<version:tag10>0100900001</version:tag10>\x01"
    firmware.write_bytes(data)

    fingerprint = tmp_path / "fingerprint.yaml"
    fingerprint.write_text(
        yaml.safe_dump(
            {
                "filename": firmware.name,
                "static": {
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "regions": [{}],
                    "version_tag": "0100900001",
                    "build_type": "debug",
                    "filesystem_preservation": False,
                    "flash_address": "0x08020000",
                },
            },
            sort_keys=False,
        )
    )

    result = subprocess.run(
        [
            str(DISCO_SCRIPT),
            "flash",
            "fingerprint",
            "test",
            str(fingerprint),
            "--static-only",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Fingerprint test failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "All tests passed" in result.stdout
