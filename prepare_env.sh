#!/usr/bin/env bash
set -euo pipefail
if [ ! -f .env ]; then
  cp .env.prod.example .env
fi
python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
s=p.read_text()
if 'troque-por-uma-chave-secreta' in s:
    s=s.replace('troque-por-uma-chave-secreta-com-muitos-caracteres', secrets.token_urlsafe(48))
if 'troque-por-uma-senha-forte-e-unica' in s:
    s=s.replace('troque-por-uma-senha-forte-e-unica', secrets.token_urlsafe(24))
p.write_text(s)
PY
echo 'Arquivo .env preparado. Agora edite DOMAIN e execute:'
echo 'docker compose -f docker-compose.prod.yml up -d --build'
