#!/bin/bash
cd /home/cloud/Projekte/BA_Ladesaeulen_Crawler_
venv/bin/python -c "
from main import fetch_data, _lade_status, _speichere_status, _lock_belegen, _lock_freigeben
import time

feeds = [
    ('EnBW_dyn',          '983100920677924864'),
    ('Tesla_dyn',         '983101210886012928'),
    ('hhenergienetz_dyn', '999766014216110080'),
    ('ecomovement_dyn',   '999765843465994240'),
    ('chargecloud_dyn',   '1006999499934756864'),
]

_lock_belegen()
try:
    status = _lade_status()
    for name, sub_id in feeds:
        status = fetch_data(name, sub_id, status)
        _speichere_status(status)
        time.sleep(10)
finally:
    _lock_freigeben()
"
