import os
import csv
import io
import json
import hashlib
import secrets
import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, Text, Boolean, ForeignKey, DateTime, select, func, or_, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware

APP_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{APP_DIR / 'chamados_ti.db'}")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
SECRET_KEY = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
APP_NAME = os.getenv("APP_NAME", "Chamados TI Hospital")

SETORES = [
    "UTI Adulto", "UTI Neonatal", "UTI Pediatrica", "Pronto Socorro",
    "Centro Cirurgico", "Centro Obstetrico", "Maternidade", "Enfermaria",
    "Ambulatorio", "Recepcao", "Farmacia", "Laboratorio", "Radiologia",
    "Diagnostico por Imagem", "Hemodialise", "Nutricao", "Almoxarifado",
    "Faturamento", "Financeiro", "Recursos Humanos", "Diretoria",
    "Administrativo", "Manutencao", "Outro",
]
MOTIVOS = [
    "Computador nao liga", "Computador lento / travando", "Sem acesso a internet",
    "Sem acesso a rede / pasta", "Impressora nao imprime", "Sistema / Prontuario com erro",
    "Esqueci a senha / acesso bloqueado", "Telefone / Ramal", "Monitor / Teclado / Mouse",
    "Instalacao de programa", "E-mail", "Etiquetas / Pulseiras / Leitor", "Outro",
]
URGENCIAS = ["Baixa", "Media", "Alta", "Critica"]
STATUS = ["Aberto", "Em atendimento", "Aguardando", "Resolvido", "Cancelado"]
PERFIS = ["master", "tecnico", "usuario"]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    usuario: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), default="usuario", nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

class Ticket(Base):
    __tablename__ = "chamados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aberto_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    aberto_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    solicitante: Mapped[str] = mapped_column(String(160), nullable=False)
    setor: Mapped[str] = mapped_column(String(120), nullable=False)
    contato: Mapped[str] = mapped_column(String(120), default="")
    motivo: Mapped[str] = mapped_column(String(180), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, default="")
    urgencia: Mapped[str] = mapped_column(String(20), default="Media", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Aberto", nullable=False)
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    solucao: Mapped[str] = mapped_column(Text, default="")
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

class History(Base):
    __tablename__ = "historico"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamados.id"), index=True, nullable=False)
    data: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    usuario: Mapped[str] = mapped_column(String(160), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)

Base.metadata.create_all(engine)

def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()

def now(): return datetime.now()
def fmt(dt): return dt.strftime("%d/%m/%Y %H:%M") if dt else ""

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return salt, h

def verify_password(password, salt, expected):
    _, h = hash_password(password, salt)
    return secrets.compare_digest(h, expected)

def ensure_admin(s: Session):
    if s.scalar(select(func.count(User.id))) == 0:
        salt, h = hash_password("admin123")
        s.add(User(nome="Administrador", usuario="admin", salt=salt, senha_hash=h,
                   perfil="master", ativo=True, trocar_senha=True))
        s.commit()

def user_dict(u):
    return {"id":u.id,"nome":u.nome,"usuario":u.usuario,"perfil":u.perfil,"ativo":u.ativo,"trocar_senha":u.trocar_senha}

def ticket_dict(t, s):
    resp = s.get(User, t.responsavel_id) if t.responsavel_id else None
    return {
        "id":t.id,"aberto_em":fmt(t.aberto_em),"aberto_por":t.aberto_por,
        "solicitante":t.solicitante,"setor":t.setor,"contato":t.contato or "",
        "motivo":t.motivo,"descricao":t.descricao or "","urgencia":t.urgencia,
        "status":t.status,"responsavel_id":t.responsavel_id,
        "responsavel":resp.nome if resp else "","solucao":t.solucao or "",
        "fechado_em":fmt(t.fechado_em),"atualizado_em":fmt(t.atualizado_em),
    }

def history_dict(h): return {"data":fmt(h.data),"usuario":h.usuario,"texto":h.texto}

def current_user(request: Request, s: Session):
    uid = request.session.get("user_id")
    if not uid: raise HTTPException(401, "Sessao expirada.")
    u = s.get(User, uid)
    if not u or not u.ativo: raise HTTPException(401, "Usuario invalido ou desativado.")
    return u

def require_staff(u):
    if u.perfil not in ("master", "tecnico"): raise HTTPException(403, "Acesso restrito a equipe de TI.")

def require_master(u):
    if u.perfil != "master": raise HTTPException(403, "Acesso restrito ao Master.")

class LoginIn(BaseModel): usuario: str; senha: str
class TicketIn(BaseModel):
    setor: str; contato: str = ""; motivo: str; descricao: str = ""; urgencia: str = "Media"
class UpdateTicket(BaseModel):
    status: str; responsavel_id: int | None = None; comentario: str = ""
class CommentIn(BaseModel): texto: str = Field(min_length=1)
class UserIn(BaseModel):
    nome: str; usuario: str; senha: str = ""; perfil: str = "usuario"; ativo: bool = True
class PasswordIn(BaseModel): nova_senha: str = Field(min_length=6)

class ConnectionManager:
    def __init__(self): self.connections: dict[int, set[WebSocket]] = {}
    async def connect(self, uid, ws):
        await ws.accept(); self.connections.setdefault(uid, set()).add(ws)
    def disconnect(self, uid, ws):
        self.connections.get(uid, set()).discard(ws)
    async def broadcast_staff(self, payload):
        dead=[]
        for uid, conns in self.connections.items():
            for ws in list(conns):
                try: await ws.send_json(payload)
                except Exception: dead.append((uid,ws))
        for uid,ws in dead: self.disconnect(uid,ws)
manager = ConnectionManager()

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60*60*12, same_site="lax", https_only=COOKIE_SECURE)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

with SessionLocal() as s: ensure_admin(s)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request":request,"app_name":APP_NAME})

@app.post("/api/login")
def login(data: LoginIn, request: Request, s: Session = Depends(db)):
    u = s.scalar(select(User).where(func.lower(User.usuario)==data.usuario.strip().lower()))
    if not u or not u.ativo or not verify_password(data.senha, u.salt, u.senha_hash):
        raise HTTPException(401, "Usuario ou senha incorretos.")
    request.session["user_id"] = u.id
    return {"ok":True,"user":user_dict(u)}

@app.post("/api/logout")
def logout(request: Request):
    request.session.clear(); return {"ok":True}

@app.get("/api/me")
def me(request: Request, s: Session=Depends(db)):
    return user_dict(current_user(request,s))

@app.get("/api/config")
def config():
    return {"setores":SETORES,"motivos":MOTIVOS,"urgencias":URGENCIAS,"status":STATUS}

@app.get("/api/dashboard")
def dashboard(request: Request, s: Session=Depends(db)):
    u=current_user(request,s); require_staff(u)
    q=select(Ticket)
    total=s.scalar(select(func.count(Ticket.id))) or 0
    abertos=s.scalar(select(func.count(Ticket.id)).where(Ticket.status=="Aberto")) or 0
    atend=s.scalar(select(func.count(Ticket.id)).where(Ticket.status=="Em atendimento")) or 0
    crit=s.scalar(select(func.count(Ticket.id)).where(Ticket.urgencia=="Critica",Ticket.status.notin_(["Resolvido","Cancelado"]))) or 0
    today=now().date()
    resol=s.scalar(select(func.count(Ticket.id)).where(Ticket.status=="Resolvido",func.date(Ticket.fechado_em)==today)) or 0
    return {"total":total,"abertos":abertos,"atendimento":atend,"criticos":crit,"resolvidos_hoje":resol}

@app.get("/api/tickets")
def tickets(request: Request, status: str="Em aberto", urgencia: str="Todas", busca: str="", s: Session=Depends(db)):
    u=current_user(request,s)
    q=select(Ticket).order_by(desc(Ticket.id))
    if u.perfil=="usuario": q=q.where(Ticket.aberto_por==u.id)
    if status=="Em aberto": q=q.where(Ticket.status.notin_(["Resolvido","Cancelado"]))
    elif status!="Todos": q=q.where(Ticket.status==status)
    if urgencia!="Todas": q=q.where(Ticket.urgencia==urgencia)
    b=busca.strip()
    if b:
        like=f"%{b}%"
        q=q.where(or_(Ticket.setor.ilike(like),Ticket.motivo.ilike(like),Ticket.solicitante.ilike(like),Ticket.descricao.ilike(like),Ticket.id==int(b[1:]) if b.startswith("#") and b[1:].isdigit() else False))
    rows=s.scalars(q.limit(500)).all()
    return [ticket_dict(t,s) for t in rows]

@app.post("/api/tickets")
async def create_ticket(data: TicketIn, request: Request, s: Session=Depends(db)):
    u=current_user(request,s)
    if data.setor not in SETORES or data.motivo not in MOTIVOS or data.urgencia not in URGENCIAS:
        raise HTTPException(400,"Dados do chamado invalidos.")
    t=Ticket(aberto_por=u.id,solicitante=u.nome,setor=data.setor,contato=data.contato.strip(),motivo=data.motivo,descricao=data.descricao.strip(),urgencia=data.urgencia,status="Aberto",atualizado_em=now())
    s.add(t); s.flush(); s.add(History(chamado_id=t.id,usuario=u.nome,texto="Chamado aberto.")); s.commit(); s.refresh(t)
    payload={"type":"novo_chamado","id":t.id,"setor":t.setor,"motivo":t.motivo,"urgencia":t.urgencia}
    await manager.broadcast_staff(payload)
    return ticket_dict(t,s)

@app.get("/api/tickets/{tid}")
def ticket_detail(tid:int, request:Request, s:Session=Depends(db)):
    u=current_user(request,s); t=s.get(Ticket,tid)
    if not t: raise HTTPException(404,"Chamado nao encontrado.")
    if u.perfil=="usuario" and t.aberto_por!=u.id: raise HTTPException(403,"Acesso negado.")
    hist=s.scalars(select(History).where(History.chamado_id==tid).order_by(History.id)).all()
    return {"ticket":ticket_dict(t,s),"historico":[history_dict(x) for x in hist]}

@app.post("/api/tickets/{tid}/update")
async def update_ticket(tid:int,data:UpdateTicket,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_staff(u)
    t=s.get(Ticket,tid)
    if not t: raise HTTPException(404,"Chamado nao encontrado.")
    if data.status not in STATUS: raise HTTPException(400,"Status invalido.")
    old_status=t.status; old_resp=t.responsavel_id
    if data.responsavel_id is not None:
        r=s.get(User,data.responsavel_id)
        if not r or not r.ativo or r.perfil not in ("master","tecnico"): raise HTTPException(400,"Responsavel invalido.")
    t.status=data.status; t.responsavel_id=data.responsavel_id; t.atualizado_em=now()
    if data.status in ("Resolvido","Cancelado") and old_status not in ("Resolvido","Cancelado"): t.fechado_em=now()
    elif data.status not in ("Resolvido","Cancelado"): t.fechado_em=None
    if old_status!=t.status: s.add(History(chamado_id=t.id,usuario=u.nome,texto=f"Status alterado: {old_status} -> {t.status}"))
    if old_resp!=t.responsavel_id:
        nome="(ninguem)" if not t.responsavel_id else s.get(User,t.responsavel_id).nome
        s.add(History(chamado_id=t.id,usuario=u.nome,texto=f"Responsavel alterado para: {nome}"))
    if data.comentario.strip():
        s.add(History(chamado_id=t.id,usuario=u.nome,texto=data.comentario.strip()))
        if data.status=="Resolvido": t.solucao=data.comentario.strip()
    s.commit(); s.refresh(t)
    await manager.broadcast_staff({"type":"chamado_atualizado","id":t.id})
    return ticket_dict(t,s)

@app.post("/api/tickets/{tid}/comment")
def comment(tid:int,data:CommentIn,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); t=s.get(Ticket,tid)
    if not t: raise HTTPException(404,"Chamado nao encontrado.")
    if u.perfil=="usuario" and t.aberto_por!=u.id: raise HTTPException(403,"Acesso negado.")
    if t.status in ("Resolvido","Cancelado"): raise HTTPException(400,"Chamado encerrado.")
    s.add(History(chamado_id=tid,usuario=u.nome,texto=data.texto.strip())); t.atualizado_em=now(); s.commit(); return {"ok":True}

@app.post("/api/tickets/{tid}/cancel")
async def cancel(tid:int,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); t=s.get(Ticket,tid)
    if not t or t.aberto_por!=u.id: raise HTTPException(403,"Acesso negado.")
    if t.status!="Aberto": raise HTTPException(400,"Somente chamados abertos podem ser cancelados.")
    t.status="Cancelado"; t.fechado_em=now(); t.atualizado_em=now(); s.add(History(chamado_id=tid,usuario=u.nome,texto="Chamado cancelado pelo solicitante.")); s.commit()
    await manager.broadcast_staff({"type":"chamado_atualizado","id":tid}); return {"ok":True}

@app.get("/api/staff")
def staff(request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_staff(u)
    return [user_dict(x) for x in s.scalars(select(User).where(User.ativo==True,User.perfil.in_(["master","tecnico"])).order_by(User.nome)).all()]

@app.get("/api/users")
def users(request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_master(u)
    return [user_dict(x) for x in s.scalars(select(User).order_by(User.nome)).all()]

@app.post("/api/users")
def create_user(data:UserIn,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_master(u)
    if data.perfil not in PERFIS: raise HTTPException(400,"Perfil invalido.")
    if not data.senha or len(data.senha)<6: raise HTTPException(400,"Informe uma senha com pelo menos 6 caracteres.")
    if s.scalar(select(User).where(func.lower(User.usuario)==data.usuario.strip().lower())): raise HTTPException(400,"Usuario ja existe.")
    salt,h=hash_password(data.senha); x=User(nome=data.nome.strip(),usuario=data.usuario.strip(),salt=salt,senha_hash=h,perfil=data.perfil,ativo=data.ativo,trocar_senha=False); s.add(x); s.commit(); s.refresh(x); return user_dict(x)

@app.put("/api/users/{uid}")
def edit_user(uid:int,data:UserIn,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_master(u); x=s.get(User,uid)
    if not x: raise HTTPException(404,"Usuario nao encontrado.")
    if data.perfil not in PERFIS: raise HTTPException(400,"Perfil invalido.")
    if data.usuario.strip().lower()!=x.usuario.lower() and s.scalar(select(User).where(func.lower(User.usuario)==data.usuario.strip().lower())): raise HTTPException(400,"Usuario ja existe.")
    x.nome=data.nome.strip(); x.usuario=data.usuario.strip(); x.perfil=data.perfil; x.ativo=data.ativo
    if data.senha:
        if len(data.senha)<6: raise HTTPException(400,"Senha muito curta.")
        x.salt,x.senha_hash=hash_password(data.senha); x.trocar_senha=False
    s.commit(); s.refresh(x); return user_dict(x)

@app.post("/api/me/password")
def change_password(data:PasswordIn,request:Request,s:Session=Depends(db)):
    u=current_user(request,s); u.salt,u.senha_hash=hash_password(data.nova_senha); u.trocar_senha=False; s.commit(); return {"ok":True}

@app.get("/api/export.csv")
def export_csv(request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_staff(u)
    rows=s.scalars(select(Ticket).order_by(Ticket.id)).all(); out=io.StringIO(); w=csv.writer(out,delimiter=";",lineterminator="\n")
    w.writerow(["Protocolo","Aberto em","Solicitante","Setor","Contato","Motivo","Urgencia","Status","Responsavel","Descricao","Solucao","Fechado em"])
    for t in rows:
        w.writerow([t.id,fmt(t.aberto_em),t.solicitante,t.setor,t.contato,t.motivo,t.urgencia,t.status,s.get(User,t.responsavel_id).nome if t.responsavel_id else "",t.descricao,t.solucao,fmt(t.fechado_em)])
    return StreamingResponse(iter([out.getvalue().encode("utf-8-sig")]),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="chamados_{now():%Y%m%d_%H%M}.csv"'})

@app.get("/api/backup.json")
def backup_json(request:Request,s:Session=Depends(db)):
    u=current_user(request,s); require_master(u)
    users=[user_dict(x) for x in s.scalars(select(User)).all()]
    tickets=[ticket_dict(x,s) for x in s.scalars(select(Ticket)).all()]
    history=[history_dict(x)|{"chamado_id":x.chamado_id} for x in s.scalars(select(History)).all()]
    payload=json.dumps({"gerado_em":now().isoformat(),"usuarios":users,"chamados":tickets,"historico":history},ensure_ascii=False,indent=2).encode("utf-8")
    return StreamingResponse(iter([payload]),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="backup_chamados_{now():%Y%m%d_%H%M}.json"'})

@app.get("/health")
def health():
    return {"status":"ok"}

@app.websocket("/ws")
async def websocket_endpoint(ws:WebSocket):
    await ws.accept()
    uid=None
    try:
        # SessionMiddleware places the signed session in the cookie; Starlette exposes it through scope.
        session=ws.scope.get("session",{})
        uid=session.get("user_id")
        if not uid:
            await ws.close(code=1008); return
        with SessionLocal() as s:
            u=s.get(User,uid)
            if not u or not u.ativo or u.perfil not in ("master","tecnico"):
                await ws.close(code=1008); return
        manager.connections.setdefault(uid,set()).add(ws)
        await ws.send_json({"type":"connected"})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if uid: manager.disconnect(uid,ws)
