# Chamados TI Hospital — versão online e moderna

Esta versão substitui o aplicativo Tkinter/SQLite compartilhado por uma aplicação web centralizada.

## O que foi alterado
- Interface moderna e responsiva, acessível pelo navegador.
- Vários PCs podem usar o sistema ao mesmo tempo.
- Usuários comuns abrem chamados normalmente.
- Master/Técnico recebem novos chamados em tempo real via WebSocket.
- Banco centralizado no servidor.
- PostgreSQL é recomendado para produção; SQLite fica disponível para teste local.
- Perfis: Master, Técnico e Usuário.
- Dashboard com indicadores.
- Filtros, busca, histórico, responsável, status, comentários e solução.
- Cadastro/edição de usuários.
- Exportação CSV.
- Backup lógico em JSON.
- Senhas com PBKDF2-HMAC-SHA256, mantendo a lógica de segurança do sistema original.

## Teste no Windows
1. Instale Python 3.11 ou mais recente.
2. Abra o Prompt nesta pasta `server`.
3. Execute:
   `python -m venv .venv`
4. Ative:
   `.venv\\Scripts\\activate`
5. Instale:
   `pip install -r requirements.txt`
6. Copie `.env.example` para `.env` e troque `SECRET_KEY`.
7. Execute:
   `uvicorn app:app --host 0.0.0.0 --port 8000`
8. Abra `http://localhost:8000`.

Login inicial: **admin / admin123**. Troque a senha imediatamente.

## Colocar realmente na internet
Para uso fora da rede do hospital, hospede esta pasta em um servidor/VPS/cloud com HTTPS e PostgreSQL. Todos os PCs passam a acessar o mesmo endereço, por exemplo `https://ti.seuhospital.com.br`.

Não coloque a porta 8000 diretamente na internet sem um proxy HTTPS/reverse proxy.

## Estrutura
- `server/app.py` — API, banco, autenticação e WebSocket.
- `server/templates/index.html` — página principal.
- `server/static/style.css` — interface moderna.
- `server/static/app.js` — lógica da aplicação.
- `server/requirements.txt` — dependências.
- `server/.env.example` — configuração.
