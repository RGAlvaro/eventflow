import base64
import json
import os


def pytest_configure() -> None:
    os.environ.setdefault(
        "EVENTFLOW_ENCRYPTION_KEYS",
        json.dumps({"test": base64.b64encode(b"T" * 32).decode("ascii")}),
    )
    os.environ.setdefault("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID", "test")
