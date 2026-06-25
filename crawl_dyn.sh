#!/bin/bash
cd /home/cloud/Projekte/BA_Ladesaeulen_Crawler_
venv/bin/python -c "
from main import fetch_data
import time
feeds = [
    ('EnBW_dyn',          '983100920677924864'),
    ('Tesla_dyn',         '983101210886012928'),
    ('hhenergienetz_dyn', '999766014216110080'),
    ('ecomovement_dyn',   '999765843465994240'),
    ('chargecloud_dyn',   '1006999499934756864'),
]
for name, sub_id in feeds:
    fetch_data(name, sub_id)
    time.sleep(10)
"
