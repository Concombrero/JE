import threading
import time
from functools import lru_cache

import requests


OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {
    "User-Agent": "MySurfaceApp/1.0"
}


SESSION = requests.Session()
SESSION.headers.update(HEADERS)

LOCK = threading.Lock()

# évite d'enchaîner trop vite les requêtes
_LAST_REQUEST_TIME = 0.0


def _log(verbose: bool, msg: str):

    if verbose:
        print(msg)


@lru_cache(maxsize=5000)
def overpass(
    query: str,
    verbose: bool = False,
    timeout: int = 120,
    max_retries: int = 3,
    min_delay: float = 1.0,
):

    global _LAST_REQUEST_TIME

    last_error = None

    for url in OVERPASS_URLS:

        _log(
            verbose,
            f"[INFO] Serveur : {url}"
        )

        retry = 0

        while retry < max_retries:

            try:

                #
                # Un seul thread à la fois et délai minimal
                #
                with LOCK:

                    elapsed = time.time() - _LAST_REQUEST_TIME

                    if elapsed < min_delay:
                        wait = min_delay - elapsed

                        _log(
                            verbose,
                            f"[INFO] Attente {wait:.1f}s"
                        )

                        time.sleep(wait)

                    _LAST_REQUEST_TIME = time.time()

                    r = SESSION.post(
                        url,
                        data=query,
                        timeout=timeout
                    )

                #
                # 429
                #
                if r.status_code == 429:

                    retry_after = r.headers.get("Retry-After")

                    if retry_after:

                        try:
                            wait_time = int(retry_after)

                        except ValueError:
                            wait_time = 30

                    else:
                        wait_time = 30

                    _log(
                        verbose,
                        f"[WARN] 429 sur {url} "
                        f"(attente {wait_time}s)"
                    )

                    time.sleep(wait_time)

                    retry += 1
                    continue

                #
                # Serveur temporairement indisponible
                #
                if r.status_code in (502, 503, 504):

                    wait_time = 5 * (retry + 1)

                    _log(
                        verbose,
                        f"[WARN] {r.status_code} sur {url} "
                        f"(attente {wait_time}s)"
                    )

                    time.sleep(wait_time)

                    retry += 1
                    continue

                #
                # Autres erreurs HTTP
                #
                r.raise_for_status()

                _log(
                    verbose,
                    f"[INFO] Succès sur {url}"
                )

                return r.json()

            except requests.exceptions.Timeout as e:

                last_error = e

                wait_time = 5 * (retry + 1)

                _log(
                    verbose,
                    f"[WARN] Timeout "
                    f"(attente {wait_time}s)"
                )

                time.sleep(wait_time)

                retry += 1

            except requests.exceptions.ConnectionError as e:

                last_error = e

                wait_time = 5 * (retry + 1)

                _log(
                    verbose,
                    f"[WARN] ConnectionError "
                    f"(attente {wait_time}s)"
                )

                time.sleep(wait_time)

                retry += 1

            except Exception as e:

                last_error = e

                _log(
                    verbose,
                    f"[WARN] Erreur : {e}"
                )

                break

        _log(
            verbose,
            "[INFO] Passage au serveur suivant"
        )

    raise RuntimeError(
        f"Tous les serveurs Overpass ont échoué : {last_error}"
    )