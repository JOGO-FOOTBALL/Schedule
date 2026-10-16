"""Opslag in Azure Blob Storage in plaats van de map data/.

Aan als SCHEDULE_BLOB_CONTAINER in .env staat, bijv. SCHEDULE_BLOB_CONTAINER=schedule-app. Anders: data/ zoals altijd.
De toegang gaat met SCHEDULE_BLOB_SAS_URL: een SAS-link die Azure zelf beperkt tot DEZE container
(rechten Read, Add, Create, Write, List; géén Delete). Een sleutel van het hele storage-account wordt niet gebruikt.

Veiligheid, dubbel: Azure laat met die SAS-link niets anders toe, en deze module zelf ook niet.
- Alleen de eigen container (naam moet met "schedule" beginnen; nooit die van de expense-claim-generator).
- Daarin alleen de vaste bestanden uit FILES, onder data/ (bijv. data/employees.csv).
- Er wordt nooit iets verwijderd; er wordt geen container aangemaakt (dat doe je zelf in de portal).

Vangnet (zonder beheerder): bij de eerste wijziging van een bestand op een dag wordt eerst de oude inhoud bewaard
als data/backup/<datum>/<bestand>. Terugzetten: python src/blob_store.py restore <datum> [bestand].
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime

import config  # noqa: F401  (laadt .env, zodat SCHEDULE_BLOB_CONTAINER ook zonder Docker gevonden wordt)

FILES = {
    "employees.csv", "schedule.csv", "staffing.csv", "match_staffing.csv", "person_rules.csv",
    "afwezigheid.csv", "zero_hours.csv", "events.csv", "shiftbase_sent.csv",
}
PREFIX = "data/"
BACKUP = PREFIX + "backup/"
FORBIDDEN = {"expense-claim-app"}  # logins van de expense-claim-generator: nooit schrijven
CACHE_SECONDS = 60  # zo vaak opnieuw ophalen (wijzigingen van een andere server); eigen wijzigingen meteen

CONTAINER = os.environ.get("SCHEDULE_BLOB_CONTAINER", "").strip()

_lock = threading.Lock()
_cache: dict[str, tuple[float, bytes | None]] = {}
_client = None
_backed_up: set[tuple[str, str]] = set()  # (datum, bestand) waarvan vandaag al een kopie is gemaakt


def enabled() -> bool:
    return bool(CONTAINER)


def _blob_name(file: str) -> str:
    if file not in FILES:
        raise ValueError(f"Not allowed to use blob file {file!r}; only {sorted(FILES)}")
    return PREFIX + file


def _backup_name(day: str, file: str) -> str:
    _blob_name(file)  # zelfde lijst met toegestane bestanden
    return f"{BACKUP}{date.fromisoformat(day).isoformat()}/{file}"


def _container():
    global _client
    if _client is None:
        if CONTAINER in FORBIDDEN or not CONTAINER.startswith("schedule"):
            raise ValueError(f"SCHEDULE_BLOB_CONTAINER={CONTAINER!r} is not allowed: use its own container "
                             f"whose name starts with 'schedule' (e.g. schedule-app)")
        from urllib.parse import urlparse

        from azure.storage.blob import ContainerClient

        from config import Secrets

        url = Secrets.SCHEDULE_BLOB_SAS_URL.strip()
        parsed = urlparse(url)
        if parsed.path.strip("/") != CONTAINER or "sig=" not in parsed.query:
            raise ValueError("SCHEDULE_BLOB_SAS_URL must be the SAS URL of the container "
                             f"{CONTAINER!r} itself (https://<account>.blob.core.windows.net/{CONTAINER}?sv=...&sig=...)")
        _client = ContainerClient.from_container_url(url)
    return _client


def read(file: str) -> bytes | None:
    """Inhoud van het bestand, of None als het (nog) niet bestaat."""
    blob = _blob_name(file)
    with _lock:
        hit = _cache.get(file)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    from azure.core.exceptions import ResourceNotFoundError

    try:
        data = _container().download_blob(blob).readall()
    except ResourceNotFoundError:
        data = None
    with _lock:
        _cache[file] = (time.monotonic(), data)
    return data


def _backup_before_change(file: str) -> None:
    """Eerste wijziging van vandaag: bewaar eerst de huidige inhoud (één kopie per bestand per dag)."""
    day = date.today().isoformat()
    if (day, file) in _backed_up:
        return
    backup = _container().get_blob_client(_backup_name(day, file))
    if not backup.exists():
        with _lock:
            _cache.pop(file, None)  # de echte huidige inhoud, niet uit het geheugen
        old = read(file)
        if old is not None:
            backup.upload_blob(old)
    _backed_up.add((day, file))


def write(file: str, data: bytes) -> None:
    blob = _blob_name(file)
    _backup_before_change(file)
    _container().upload_blob(blob, data, overwrite=True)
    with _lock:
        _cache[file] = (time.monotonic(), data)


def upload_local(data_dir) -> None:
    """Eenmalig: zet de bestanden uit data/ in de eigen container. Wat daar al staat, wordt NIET overschreven."""
    from pathlib import Path

    for file in sorted(FILES):
        path = Path(data_dir) / file
        if not path.exists():
            print(f"   skip      {file} (not in {data_dir})")
        elif _container().get_blob_client(_blob_name(file)).exists():
            print(f"   skip      {file} (already in the blob, not overwritten)")
        else:
            _container().upload_blob(_blob_name(file), path.read_bytes())
            print(f"   uploaded  {file}")


def restore(day: str, only: str | None = None) -> None:
    """Zet de kopie van `day` terug (alle bestanden, of alleen `only`). De huidige versie wordt eerst zelf bewaard."""
    for file in sorted(FILES if only is None else {only}):
        backup = _container().get_blob_client(_backup_name(day, file))
        if not backup.exists():
            print(f"   skip      {file} (no backup on {day})")
            continue
        with _lock:
            _cache.pop(file, None)
        current = read(file)
        if current is not None:  # huidige versie apart bewaren, zodat terugzetten zelf ook terug te draaien is
            stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
            _container().get_blob_client(f"{BACKUP}before-restore/{stamp}/{_blob_name(file)[len(PREFIX):]}")                 .upload_blob(current)
        write(file, backup.download_blob().readall())
        print(f"   restored  {file} from {day}" + (f" (previous version kept in {BACKUP}before-restore/{stamp}/)"
                                                    if current is not None else ""))


if __name__ == "__main__":
    # Vanuit de projectmap, met SCHEDULE_BLOB_CONTAINER in .env:
    #   python src/blob_store.py                          -> laat zien wat er in de eigen container staat
    #   python src/blob_store.py upload                   -> zet data/ eenmalig over (overschrijft niets)
    #   python src/blob_store.py restore 2026-10-15       -> alles terug naar hoe het die dag was
    #   python src/blob_store.py restore 2026-10-15 schedule.csv   -> alleen het rooster
    import sys

    import storage

    if not CONTAINER:
        raise SystemExit("Set SCHEDULE_BLOB_CONTAINER in .env first (e.g. SCHEDULE_BLOB_CONTAINER=schedule-app).")
    print(f"Container: {CONTAINER} (only the files under {PREFIX} are used)")
    if len(sys.argv) > 1 and sys.argv[1] == "upload":
        upload_local(storage.DATA_DIR)
    if len(sys.argv) > 2 and sys.argv[1] == "restore":
        restore(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    for b in _container().list_blobs(name_starts_with=PREFIX):
        print(f"   {b.name:<32} {b.size:>8} bytes   {b.last_modified:%Y-%m-%d %H:%M}")
