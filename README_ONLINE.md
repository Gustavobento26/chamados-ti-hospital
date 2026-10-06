# Chamados TI Hospital — publicação 100% online

Esta versão usa:
- FastAPI
- PostgreSQL
- Docker Compose
- Caddy com HTTPS automático
- WebSocket para avisos em tempo real

## Resultado final

Todos os PCs usam um único endereço, por exemplo:

https://chamados.seudominio.com.br

Não é necessário instalar o programa em cada PC.

## O que é necessário

1. Um VPS/servidor Linux com Docker e Docker Compose.
2. Um domínio ou subdomínio.
3. Um registro DNS apontando para o IP público do VPS.
4. Portas TCP 80 e 443 liberadas no firewall do servidor.

## Configuração

1. Copie `.env.prod.example` para `.env`.
2. Preencha `DOMAIN`, `POSTGRES_PASSWORD` e `SECRET_KEY`.
3. Execute:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. Consulte os logs:

```bash
docker compose -f docker-compose.prod.yml logs -f app
```

5. Abra o domínio no navegador.

O Caddy solicita e renova o certificado HTTPS automaticamente quando o DNS já estiver apontando para o servidor e as portas 80/443 estiverem acessíveis.

## Login inicial

Usuário: `admin`
Senha: `admin123`

Troque a senha imediatamente após o primeiro acesso.

## Backup PostgreSQL

Execute periodicamente no servidor:

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U chamados -d chamados_ti > backup_chamados.sql
```

Guarde os backups fora do servidor.

## Atualização

Depois de substituir o código por uma nova versão:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

O volume `postgres_data` preserva o banco.

## Observação sobre os dados do teste local

O banco `server/chamados_ti.db` usado no teste local é SQLite. Ele não é o banco de produção. Para levar chamados e usuários atuais para PostgreSQL, faça uma migração antes da entrada em produção; não apague o SQLite até conferir os dados migrados.
