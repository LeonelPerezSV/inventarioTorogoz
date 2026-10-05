
import os, io, csv, zipfile, hashlib, secrets
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, LargeBinary, inspect as sa_inspect, text as sa_text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError

APP_NAME='Control de Inventario y Activo Fijo'
BASE_DIR=Path(__file__).resolve().parent
DB_PATH=BASE_DIR/'inventario_activo_fijo.db'
BACKUP_DIR=BASE_DIR/'backups'; BACKUP_DIR.mkdir(exist_ok=True)
DATABASE_URL=os.getenv('DATABASE_URL', f'sqlite:///{DB_PATH}')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql+psycopg2://',1)
engine=create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base=declarative_base()

BLOCKS_MASTER=[
(1,'CI-FINANCIEROS'),
(2,'CI-OTROS'),
(3,'CI-PERSONAL'),
(4,'LOC-ACCESTANQ'),
(5,'LOC-AMBIENT&SOC'),
(6,'LOC-BALANCESECTORIZ'),
(7,'LOC-CATAST'),
(8,'LOC-COMUNIC'),
(9,'LOC-DAAB'),
(10,'LOC-DEMOLTANQ'),
(11,'LOC-ESCALTANQ'),
(12,'LOC-FRAUDEUSUAR'),
(13,'LOC-GEOREFSECT'),
(14,'LOC-GISSECTORIZ'),
(15,'LOC-IMPERMTANQ'),
(16,'LOC-INSTALEQ-ACOM'),
(17,'LOC-INSTAL-EQMEDIC'),
(18,'LOC-INSTAL-MACRCLAP'),
(19,'LOC-INSTAL-MACRELEC'),
(20,'LOC-INSTAL-MEDIDWOL'),
(21,'LOC-INSTAL-REPARACTUB'),
(22,'LOC-INSTAL-TAPON'),
(23,'LOC-INSTALTUB-PH'),
(24,'LOC-INSTALTUB-ZANJA'),
(25,'LOC-INSTAL-VALVAIR'),
(26,'LOC-INSTAL-VALVCHECK'),
(27,'LOC-INSTAL-VALVCOMP'),
(28,'LOC-INSTAL-VALVFLOT'),
(29,'LOC-INSTAL-VALVMARIP'),
(30,'LOC-INSTAL-VALVREG'),
(31,'LOC-INST-SELLOMICROM'),
(32,'LOC-IRREGCOMUN'),
(33,'LOC-IRREGUSUAR'),
(34,'LOC-MODSECTORIZ'),
(35,'LOC-MUROTANQ'),
(36,'LOC-OC-ACCTANQ'),
(37,'LOC-OC-CAJASMEDIC'),
(38,'LOC-OC-CAJASREGUL'),
(39,'LOC-OC-CAJASVISITA'),
(40,'LOC-OC-POZOSVISITA'),
(41,'LOC-PASOAERETUB'),
(42,'LOC-PINTTANQ'),
(43,'LOC-PINTTANQ-ALTO'),
(44,'LOC-PRELIM-PH'),
(45,'LOC-PRUEBPRES'),
(46,'LOC-RASTRFUG'),
(47,'LOC-REPORTFUG'),
(48,'LOC-REPOSIC-ACOM'),
(49,'LOC-REPOSIC-ZANJATUB'),
(50,'LOC-SONDEOEXPL'),
(51,'LOC-TAPACAJAVIST'),
(52,'LOC-TAPAPOZOSVIST'),
(53,'LOC-ZANJA-ACOM'),
(54,'LOC-ZANJA-REPARTUB'),
(55,'LOC-ZANJA-TUB'),
(56,'TRANSF-CAJAS-ACOM'),
(57,'TRANSF-COLLAR-ACOM'),
(58,'TRANSF-EQLOCFUGA'),
(59,'TRANSF-EQLOCTUB'),
(60,'TRANSF-EQMEDIC'),
(61,'TRANSF-GEORADAR'),
(62,'TRANSF-KITREPARACTUB'),
(63,'TRANSF-MACRCLAP'),
(64,'TRANSF-MACRELEC'),
(65,'TRANSF-MEDIDWOL'),
(66,'TRANSF-MEDNIVELTANQ'),
(67,'TRANSF-MICROM-ACOM'),
(68,'TRANSF-ODOM'),
(69,'TRANSF-SELLOMICROMED'),
(70,'TRANSF-TAPON'),
(71,'TRANSF-TUBHFD'),
(72,'TRANSF-TUBPEAD'),
(73,'TRANSF-VALV-ACOM'),
(74,'TRANSF-VALVAIR'),
(75,'TRANSF-VALVCHECK'),
(76,'TRANSF-VALVCOMP'),
(77,'TRANSF-VALVFLOT'),
(78,'TRANSF-VALVMARIP'),
(79,'TRANSF-VALVREG')
]

def now(): return datetime.now()
def db(): return SessionLocal()

class Role(Base):
    __tablename__='roles'; id=Column(Integer, primary_key=True); name=Column(String(80), unique=True, nullable=False); description=Column(Text); active=Column(Boolean, default=True); users=relationship('User', back_populates='role')
class Permission(Base):
    __tablename__='permissions'; id=Column(Integer, primary_key=True); code=Column(String(100), unique=True, nullable=False); description=Column(Text, nullable=False)
class RolePermission(Base):
    __tablename__='role_permissions'; role_id=Column(Integer, ForeignKey('roles.id'), primary_key=True); permission_id=Column(Integer, ForeignKey('permissions.id'), primary_key=True)
class User(Base):
    __tablename__='users'; id=Column(Integer, primary_key=True); username=Column(String(80), unique=True, nullable=False); full_name=Column(String(160), nullable=False); password_salt=Column(String(128), nullable=False); password_hash=Column(String(256), nullable=False); role_id=Column(Integer, ForeignKey('roles.id'), nullable=False); active=Column(Boolean, default=True); must_change_password=Column(Boolean, default=False); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); role=relationship('Role', back_populates='users')
class Block(Base):
    __tablename__='blocks'; id=Column(Integer, primary_key=True); number=Column(Integer, nullable=False); code=Column(String(120), unique=True, nullable=False); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime)
class Attachment(Base):
    __tablename__='attachments'; id=Column(Integer, primary_key=True); related_type=Column(String(40), nullable=False); related_id=Column(Integer, nullable=False); filename=Column(String(260), nullable=False); content_type=Column(String(120)); data=Column(LargeBinary, nullable=False); created_at=Column(DateTime, default=now); user_id=Column(Integer, ForeignKey('users.id'))
class Warehouse(Base):
    __tablename__='warehouses'; id=Column(Integer, primary_key=True); name=Column(String(120), unique=True, nullable=False); description=Column(Text); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class Item(Base):
    __tablename__='items'; id=Column(Integer, primary_key=True); sku=Column(String(80), unique=True, nullable=False); description=Column(String(250), nullable=False); unit=Column(String(40), default='Unidad', nullable=False); minimum_stock=Column(Float, default=0); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class StockMove(Base):
    __tablename__='stock_moves'; id=Column(Integer, primary_key=True); move_date=Column(Date, nullable=False); item_id=Column(Integer, ForeignKey('items.id'), nullable=False); warehouse_id=Column(Integer, ForeignKey('warehouses.id'), nullable=False); block_id=Column(Integer, ForeignKey('blocks.id')); move_type=Column(String(40), nullable=False); quantity=Column(Float, nullable=False); unit_cost=Column(Float, default=0); document=Column(String(180)); notes=Column(Text); status=Column(String(40), default='Registrado'); reversal_of=Column(Integer, ForeignKey('stock_moves.id')); annulled_by=Column(Integer, ForeignKey('users.id')); annulled_at=Column(DateTime); annul_reason=Column(Text); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id')); item=relationship('Item'); warehouse=relationship('Warehouse'); block=relationship('Block')
class DepRule(Base):
    __tablename__='depreciation_rules'; id=Column(Integer, primary_key=True); category=Column(String(120), unique=True, nullable=False); annual_rate=Column(Float, nullable=False); useful_life_years=Column(Float, nullable=False); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class Asset(Base):
    __tablename__='assets'; id=Column(Integer, primary_key=True); asset_code=Column(String(80), unique=True, nullable=False); description=Column(String(250), nullable=False); category=Column(String(120), nullable=False); acquisition_date=Column(Date, nullable=False); in_service_date=Column(Date, nullable=False); acquisition_cost=Column(Float, nullable=False); residual_value=Column(Float, default=0); responsible=Column(String(160)); location=Column(String(160)); supplier=Column(String(180)); document=Column(String(180)); block_id=Column(Integer, ForeignKey('blocks.id')); status=Column(String(40), default='Activo'); notes=Column(Text); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class AuditLog(Base):
    __tablename__='audit_log'; id=Column(Integer, primary_key=True); table_name=Column(String(80), nullable=False); record_id=Column(Integer, nullable=False); action=Column(String(80), nullable=False); detail=Column(Text); user_id=Column(Integer, ForeignKey('users.id')); created_at=Column(DateTime, default=now)
class BackupLog(Base):
    __tablename__='backup_log'; id=Column(Integer, primary_key=True); file_name=Column(String(240), nullable=False); file_path=Column(Text, nullable=False); backup_type=Column(String(40), nullable=False); user_id=Column(Integer, ForeignKey('users.id')); created_at=Column(DateTime, default=now)

PERMISSIONS={
'dashboard.view':'Ver dashboard','items.view':'Ver productos','items.create':'Crear productos','items.edit':'Editar productos','items.delete':'Desactivar/eliminar productos','warehouses.view':'Ver bodegas','warehouses.create':'Crear bodegas','warehouses.edit':'Editar bodegas','warehouses.delete':'Desactivar/eliminar bodegas','blocks.view':'Ver bloques','blocks.manage':'Administrar bloques','moves.view':'Ver Kardex/movimientos','moves.create':'Crear movimientos','moves.edit':'Editar movimientos','moves.annul':'Anular movimientos','assets.view':'Ver activos fijos','assets.create':'Crear activos fijos','assets.edit':'Editar activos fijos','assets.delete':'Dar de baja/eliminar activos','deprules.view':'Ver reglas depreciación','deprules.manage':'Administrar reglas depreciación','users.manage':'Administrar usuarios/roles','backup.manage':'Respaldos','audit.view':'Bitácora'}
ROLE_PERMISSION_MAP={'Administrador':list(PERMISSIONS.keys()),'Supervisor':['dashboard.view','items.view','items.create','items.edit','warehouses.view','warehouses.create','warehouses.edit','blocks.view','blocks.manage','moves.view','moves.create','moves.edit','moves.annul','assets.view','assets.create','assets.edit','assets.delete','deprules.view','deprules.manage','backup.manage','audit.view'],'Bodega':['dashboard.view','items.view','warehouses.view','blocks.view','moves.view','moves.create','assets.view'],'Activo fijo':['dashboard.view','blocks.view','assets.view','assets.create','assets.edit','assets.delete','deprules.view','moves.view'],'Consulta':['dashboard.view','items.view','warehouses.view','blocks.view','moves.view','assets.view','deprules.view']}

def hash_password(password, salt=None):
    salt=salt or secrets.token_hex(16); h=hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 150000).hex(); return salt,h
def verify_password(password,salt,h): return secrets.compare_digest(hash_password(password,salt)[1], h)


def ensure_schema():
    insp=sa_inspect(engine)
    def cols(table):
        return {c['name'] for c in insp.get_columns(table)} if insp.has_table(table) else set()
    with engine.begin() as con:
        if insp.has_table('stock_moves') and 'block_id' not in cols('stock_moves'):
            con.execute(sa_text('ALTER TABLE stock_moves ADD COLUMN block_id INTEGER'))
        if insp.has_table('assets') and 'block_id' not in cols('assets'):
            con.execute(sa_text('ALTER TABLE assets ADD COLUMN block_id INTEGER'))

def get_blocks(active_only=True):
    s=db()
    q=s.query(Block)
    if active_only: q=q.filter_by(active=True)
    rows=q.order_by(Block.number,Block.code).all()
    s.close()
    return rows

def block_options(blocks, include_empty=False):
    opts=['Sin bloque'] if include_empty else []
    opts += [f'{b.id} | {b.number} - {b.code}' for b in blocks]
    return opts

def parse_block_id(selected):
    if not selected or selected=='Sin bloque': return None
    return int(str(selected).split(' | ')[0])

def default_block_option(blocks, block_id, include_empty=True):
    opts=block_options(blocks, include_empty=include_empty)
    if block_id:
        pref=f'{block_id} |'
        for opt in opts:
            if opt.startswith(pref): return opt
    return opts[0] if opts else 'Sin bloque'

def block_label(block):
    return f'{block.number} - {block.code}' if block else 'Sin bloque'

def attachment_counts(related_type):
    s=db()
    rows=s.query(Attachment).filter_by(related_type=related_type).all()
    s.close()
    counts={}
    for a in rows:
        counts[a.related_id]=counts.get(a.related_id,0)+1
    return counts

def save_attachment(uploaded_file, related_type, related_id):
    if not uploaded_file: return None
    data=uploaded_file.getvalue()
    if not data: return None
    s=db()
    try:
        att=Attachment(related_type=related_type, related_id=int(related_id), filename=uploaded_file.name, content_type=getattr(uploaded_file,'type',None), data=data, user_id=st.session_state.get('user_id'))
        s.add(att); s.commit(); aid=att.id
    finally:
        s.close()
    audit('attachments',aid,'CREATE',f'{related_type} {related_id} - {uploaded_file.name}')
    return aid

def attachments_download_panel(related_type, title):
    st.subheader(title)
    s=db()
    rows=s.query(Attachment).filter_by(related_type=related_type).order_by(Attachment.created_at.desc()).all()
    s.close()
    if not rows:
        st.info('No hay documentos adjuntos todavía.')
        return
    selected=st.selectbox('Documento adjunto',[f'{a.id} | {a.related_type} #{a.related_id} | {a.filename} | {a.created_at}' for a in rows],key=f'doc_{related_type}')
    aid=int(selected.split(' | ')[0])
    att=next(a for a in rows if a.id==aid)
    st.download_button('Descargar documento',att.data,att.filename,att.content_type or 'application/octet-stream')

def show_filterable_table(df, key, height=540):
    if df.empty:
        st.info('No hay datos para mostrar.')
        return
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder
        gb=GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(filter=True, sortable=True, resizable=True, floatingFilter=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=25)
        AgGrid(df, gridOptions=gb.build(), height=height, fit_columns_on_grid_load=False, theme='streamlit', key=key)
    except Exception:
        st.dataframe(df,width='stretch')
        st.caption('Vista alternativa: instala/actualiza streamlit-aggrid para filtros directamente en encabezados.')


def init_db():
    Base.metadata.create_all(bind=engine); ensure_schema(); s=db()
    try:
        # FIX3: las reversas son registros de trazabilidad, no movimientos operativos.
        # Si una versión anterior dejó reversas como 'Registrado', se corrigen automáticamente.
        try:
            s.query(StockMove).filter(StockMove.reversal_of.isnot(None), StockMove.status=='Registrado').update({StockMove.status:'Reversa'}, synchronize_session=False)
            s.commit()
        except Exception:
            s.rollback()
        for code,desc in PERMISSIONS.items():
            if not s.query(Permission).filter_by(code=code).first(): s.add(Permission(code=code, description=desc))
        s.commit()
        for rn,codes in ROLE_PERMISSION_MAP.items():
            role=s.query(Role).filter_by(name=rn).first()
            if not role: role=Role(name=rn, description=f'Rol {rn}'); s.add(role); s.commit()
            existing={rp.permission_id for rp in s.query(RolePermission).filter_by(role_id=role.id)}
            for code in codes:
                p=s.query(Permission).filter_by(code=code).first()
                if p and p.id not in existing: s.add(RolePermission(role_id=role.id, permission_id=p.id))
            s.commit()
        admin_role=s.query(Role).filter_by(name='Administrador').first()
        if not s.query(User).filter_by(username='admin').first():
            salt,h=hash_password('admin123'); s.add(User(username='admin', full_name='Administrador', password_salt=salt, password_hash=h, role_id=admin_role.id, active=True, must_change_password=True)); s.commit()
        if not s.query(Warehouse).filter_by(name='Bodega Principal').first(): s.add(Warehouse(name='Bodega Principal', description='Bodega inicial')); s.commit()
        for num,code in BLOCKS_MASTER:
            b=s.query(Block).filter_by(code=code).first()
            if not b: s.add(Block(number=num,code=code,active=True))
            else: b.number=num; b.active=True
        s.commit()
        for cat,rate,life in [('Edificaciones',0.05,20),('Maquinaria',0.20,5),('Vehículos',0.25,4),('Otros bienes muebles',0.50,2)]:
            if not s.query(DepRule).filter_by(category=cat).first(): s.add(DepRule(category=cat, annual_rate=rate, useful_life_years=life)); s.commit()
    finally: s.close()

def audit(table, rid, action, detail=''):
    s=db(); s.add(AuditLog(table_name=table, record_id=int(rid or 0), action=action, detail=detail, user_id=st.session_state.get('user_id'))); s.commit(); s.close()

def get_perms(uid):
    s=db()
    try:
        u=s.query(User).filter_by(id=uid, active=True).first()
        if not u: return set()
        rows=s.query(Permission.code).join(RolePermission,RolePermission.permission_id==Permission.id).filter(RolePermission.role_id==u.role_id).all(); return {r[0] for r in rows}
    finally: s.close()
def has_perm(code): return code in st.session_state.get('permissions', set())
def require_perm(code):
    if not has_perm(code): st.error('No tienes permiso para esta opción.'); st.stop()

def move_effect(t,q): return q if t in ('Entrada','Devolución entrada') else (-q if t in ('Salida','Devolución salida') else 0)
def current_stock(item_id, wh_id, block_id=None, exclude=None):
    s=db(); q=s.query(StockMove).filter(StockMove.item_id==item_id, StockMove.warehouse_id==wh_id, StockMove.status=='Registrado', StockMove.reversal_of.is_(None))
    q=q.filter(StockMove.block_id==block_id) if block_id is not None else q.filter(StockMove.block_id.is_(None))
    if exclude: q=q.filter(StockMove.id!=exclude)
    total=sum(move_effect(m.move_type,m.quantity) for m in q.all()); s.close(); return total

def inventory_df():
    s=db(); rows=s.query(StockMove,Item,Warehouse,Block).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None)).all(); s.close(); data={}; ent={}
    for m,i,w,b in rows:
        bloque=block_label(b); k=(i.id,w.id,m.block_id,i.sku,i.description,w.name,bloque,i.minimum_stock); data[k]=data.get(k,0)+move_effect(m.move_type,m.quantity); ent.setdefault(k,[0,0])
        if m.move_type in ('Entrada','Devolución entrada'): ent[k][0]+=m.quantity; ent[k][1]+=m.quantity*m.unit_cost
    out=[]
    for k,stock in data.items():
        item_id,wh_id,block_id,sku,desc,wh,bloque,minimo=k; avg=ent[k][1]/ent[k][0] if ent[k][0] else 0
        out.append({'item_id':item_id,'warehouse_id':wh_id,'block_id':block_id,'Código':sku,'Producto':desc,'Bodega':wh,'Bloque':bloque,'Existencia':round(stock,4),'Costo promedio ref.':round(avg,4),'Valor estimado':round(stock*avg,2),'Stock mínimo':minimo,'Alerta':'Bajo mínimo' if stock<=minimo else ''})
    return pd.DataFrame(out)

def dep_schedule(a, rate):
    cost=float(a.acquisition_cost); residual=float(a.residual_value or 0); base=max(cost-residual,0); annual=base*float(rate); today=date.today(); acc=0; rows=[]
    for y in range(a.in_service_date.year, today.year+1):
        ys,ye=date(y,1,1),date(y,12,31); start=max(a.in_service_date,ys); end=min(today,ye)
        if end<start or acc>=base: continue
        days=(end-start).days+1; ydays=(ye-ys).days+1; dep=min(annual*days/ydays, base-acc); acc+=dep
        rows.append({'Año':y,'Días depreciados':days,'Depreciación':round(dep,2),'Dep. acumulada':round(acc,2),'Valor en libros':round(cost-acc,2)})
    return pd.DataFrame(rows)

def export_backup(kind='manual'):
    ts=datetime.now().strftime('%Y%m%d_%H%M%S'); path=BACKUP_DIR/f'backup_{kind}_{ts}.zip'; s=db()
    try:
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for name,cls in {'items':Item,'warehouses':Warehouse,'blocks':Block,'stock_moves':StockMove,'assets':Asset,'depreciation_rules':DepRule,'users':User,'roles':Role,'audit_log':AuditLog}.items():
                out=io.StringIO(); rows=s.query(cls).all(); writer=None
                for r in rows:
                    d={k:v for k,v in r.__dict__.items() if not k.startswith('_')}
                    if writer is None: writer=csv.DictWriter(out,fieldnames=list(d.keys())); writer.writeheader()
                    writer.writerow(d)
                z.writestr(name+'.csv', out.getvalue())
            meta=io.StringIO(); writer=csv.DictWriter(meta,fieldnames=['id','related_type','related_id','filename','content_type','created_at','user_id']); writer.writeheader()
            for a in s.query(Attachment).all():
                writer.writerow({'id':a.id,'related_type':a.related_type,'related_id':a.related_id,'filename':a.filename,'content_type':a.content_type,'created_at':a.created_at,'user_id':a.user_id})
                safe=''.join(ch if ch.isalnum() or ch in (' ','_','-','.') else '_' for ch in a.filename)
                z.writestr(f'attachments/{a.id}_{safe}', a.data)
            z.writestr('attachments_metadata.csv', meta.getvalue())
            if DATABASE_URL.startswith('sqlite') and DB_PATH.exists(): z.write(DB_PATH,'inventario_activo_fijo.db')
        s.add(BackupLog(file_name=path.name,file_path=str(path),backup_type=kind,user_id=st.session_state.get('user_id'))); s.commit(); return path
    finally: s.close()

def daily_backup():
    key='bkp_'+date.today().isoformat()
    if st.session_state.get(key): return
    s=db(); exists=s.query(BackupLog).filter(BackupLog.backup_type=='automatico', BackupLog.created_at>=datetime.combine(date.today(), datetime.min.time())).first(); s.close()
    if not exists: export_backup('automatico')
    st.session_state[key]=True

init_db(); st.set_page_config(page_title=APP_NAME,page_icon='📦',layout='wide')
logo=BASE_DIR/'assets'/'logo.jpeg'

def login_screen():
    c1,c2,c3=st.columns([1,1.2,1])
    with c2:
        if logo.exists(): st.image(str(logo), width=360)
        st.title(APP_NAME); st.caption('Inicio de sesión')
        with st.form('login'):
            u=st.text_input('Usuario'); p=st.text_input('Contraseña',type='password'); ok=st.form_submit_button('Ingresar',width='stretch')
        if ok:
            s=db()
            try:
                user=s.query(User).filter_by(username=u.strip(),active=True).first()
                if not user or not verify_password(p,user.password_salt,user.password_hash):
                    st.error('Usuario o contraseña incorrectos.')
                    return
                role=s.query(Role).filter_by(id=user.role_id).first()
                role_name=role.name if role else 'Sin rol'
                user_data={
                    'authenticated':True,
                    'user_id':user.id,
                    'username':user.username,
                    'full_name':user.full_name,
                    'role_id':user.role_id,
                    'role_name':role_name,
                    'must_change_password':user.must_change_password
                }
            finally:
                s.close()
            st.session_state.update(user_data)
            st.session_state['permissions']=get_perms(user_data['user_id'])
            audit('users',user_data['user_id'],'LOGIN','Inicio de sesión')
            st.rerun()
        st.info('Usuario inicial: admin / admin123')
if not st.session_state.get('authenticated'): login_screen(); st.stop()
if st.session_state.get('must_change_password'):
    st.warning('Debes cambiar la contraseña inicial.');
    with st.form('pwd'):
        p1=st.text_input('Nueva contraseña',type='password'); p2=st.text_input('Confirmar contraseña',type='password'); ok=st.form_submit_button('Cambiar')
    if ok:
        if len(p1)<8: st.error('Mínimo 8 caracteres.')
        elif p1!=p2: st.error('No coinciden.')
        else:
            s=db(); user=s.get(User,st.session_state['user_id']); salt,h=hash_password(p1); user.password_salt=salt; user.password_hash=h; user.must_change_password=False; user.updated_at=now(); s.commit(); s.close(); audit('users',st.session_state['user_id'],'CHANGE_PASSWORD','Cambio inicial'); st.session_state['must_change_password']=False; st.rerun()
    st.stop()
daily_backup()
with st.sidebar:
    if logo.exists(): st.image(str(logo), width=220)
    st.markdown(f"**{st.session_state['full_name']}**"); st.caption('Rol: '+st.session_state['role_name'])
    if st.button('Cerrar sesión',width='stretch'): st.session_state.clear(); st.rerun()
    opts=[]
    for name,perm in [('Dashboard','dashboard.view'),('Productos','items.view'),('Bodegas','warehouses.view'),('Bloques','blocks.view'),('Movimientos Kardex','moves.view'),('Existencias','moves.view'),('Activos fijos','assets.view'),('Depreciación','assets.view'),('Reglas depreciación','deprules.view'),('Usuarios y roles','users.manage'),('Respaldos','backup.manage'),('Bitácora','audit.view')]:
        if has_perm(perm): opts.append(name)
    menu=st.radio('Menú',opts)
st.title(APP_NAME)

if menu=='Dashboard':
    require_perm('dashboard.view'); inv=inventory_df(); s=db(); ic=s.query(Item).filter_by(active=True).count(); wc=s.query(Warehouse).filter_by(active=True).count(); mc=s.query(StockMove).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None)).count(); ac=s.query(Asset).filter_by(active=True,status='Activo').count(); at=sum(a.acquisition_cost for a in s.query(Asset).filter_by(active=True).all()); s.close()
    c1,c2,c3,c4,c5=st.columns(5); c1.metric('Productos',ic); c2.metric('Bodegas',wc); c3.metric('Movimientos',mc); c4.metric('Activos',ac); c5.metric('Valor activos',f'${at:,.2f}')
    st.subheader('Existencias'); st.dataframe(inv.drop(columns=[c for c in ['item_id','warehouse_id','block_id'] if c in inv.columns]),width='stretch')
elif menu=='Productos':
    require_perm('items.view'); tabs=st.tabs(['Consultar','Crear','Editar','Desactivar / eliminar'])
    with tabs[0]:
        s=db(); rows=s.query(Item).order_by(Item.description).all(); s.close(); st.dataframe(pd.DataFrame([{'ID':r.id,'Código':r.sku,'Descripción':r.description,'Unidad':r.unit,'Stock mínimo':r.minimum_stock,'Activo':'Sí' if r.active else 'No'} for r in rows]),width='stretch')
    with tabs[1]:
        require_perm('items.create')
        with st.form('new_item',clear_on_submit=True):
            c1,c2,c3,c4=st.columns(4); sku=c1.text_input('Código/SKU'); desc=c2.text_input('Descripción'); unit=c3.text_input('Unidad','Unidad'); minimo=c4.number_input('Stock mínimo',min_value=0.0,value=0.0)
            if st.form_submit_button('Crear'):
                s=db(); it=Item(sku=sku.strip(),description=desc.strip(),unit=unit.strip() or 'Unidad',minimum_stock=minimo,created_by=st.session_state['user_id']); s.add(it)
                try: s.commit(); audit('items',it.id,'CREATE',it.sku); st.success('Producto creado.')
                except IntegrityError: s.rollback(); st.error('Código duplicado.')
                finally: s.close()
    with tabs[2]:
        require_perm('items.edit'); s=db(); items=s.query(Item).order_by(Item.description).all(); s.close()
        if items:
            sel=st.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items]); iid=int(sel.split(' | ')[0]); s=db(); it=s.get(Item,iid)
            with st.form('edit_item'):
                c1,c2,c3,c4=st.columns(4); sku=c1.text_input('Código',it.sku); desc=c2.text_input('Descripción',it.description); unit=c3.text_input('Unidad',it.unit); minimo=c4.number_input('Stock mínimo',min_value=0.0,value=float(it.minimum_stock)); active=st.checkbox('Activo',it.active)
                if st.form_submit_button('Guardar'):
                    it.sku=sku.strip(); it.description=desc.strip(); it.unit=unit.strip() or 'Unidad'; it.minimum_stock=minimo; it.active=active; it.updated_at=now(); it.updated_by=st.session_state['user_id']
                    try: s.commit(); audit('items',iid,'UPDATE',sku); st.success('Actualizado.')
                    except IntegrityError: s.rollback(); st.error('Código duplicado.')
            s.close()
    with tabs[3]:
        require_perm('items.delete'); s=db(); items=s.query(Item).order_by(Item.description).all(); sel=st.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items],key='del_item') if items else None
        if sel:
            iid=int(sel.split(' | ')[0]); it=s.get(Item,iid); moves=s.query(StockMove).filter_by(item_id=iid).count(); c1,c2=st.columns(2)
            if c1.button('Desactivar'): it.active=False; it.updated_at=now(); s.commit(); audit('items',iid,'DEACTIVATE',it.sku); st.success('Desactivado.')
            if moves: c2.warning('No se puede eliminar porque tiene movimientos.')
            elif c2.button('Eliminar físicamente'): s.delete(it); s.commit(); audit('items',iid,'DELETE','Eliminado'); st.success('Eliminado.')
        s.close()
elif menu=='Bodegas':
    require_perm('warehouses.view'); tabs=st.tabs(['Consultar','Crear','Editar','Desactivar / eliminar'])
    with tabs[0]:
        s=db(); rows=s.query(Warehouse).order_by(Warehouse.name).all(); s.close(); st.dataframe(pd.DataFrame([{'ID':r.id,'Bodega':r.name,'Descripción':r.description,'Activa':'Sí' if r.active else 'No'} for r in rows]),width='stretch')
    with tabs[1]:
        require_perm('warehouses.create')
        with st.form('new_wh',clear_on_submit=True):
            name=st.text_input('Nombre'); desc=st.text_area('Descripción')
            if st.form_submit_button('Crear'):
                s=db(); w=Warehouse(name=name.strip(),description=desc.strip(),created_by=st.session_state['user_id']); s.add(w)
                try: s.commit(); audit('warehouses',w.id,'CREATE',w.name); st.success('Bodega creada.')
                except IntegrityError: s.rollback(); st.error('Bodega duplicada.')
                finally: s.close()
    with tabs[2]:
        require_perm('warehouses.edit'); s=db(); whs=s.query(Warehouse).order_by(Warehouse.name).all(); s.close()
        if whs:
            sel=st.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs]); wid=int(sel.split(' | ')[0]); s=db(); w=s.get(Warehouse,wid)
            with st.form('edit_wh'):
                name=st.text_input('Nombre',w.name); desc=st.text_area('Descripción',w.description or ''); active=st.checkbox('Activa',w.active)
                if st.form_submit_button('Guardar'): w.name=name.strip(); w.description=desc.strip(); w.active=active; w.updated_at=now(); s.commit(); audit('warehouses',wid,'UPDATE',w.name); st.success('Actualizada.')
            s.close()
    with tabs[3]:
        require_perm('warehouses.delete'); s=db(); whs=s.query(Warehouse).order_by(Warehouse.name).all(); sel=st.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs],key='del_wh') if whs else None
        if sel:
            wid=int(sel.split(' | ')[0]); w=s.get(Warehouse,wid); moves=s.query(StockMove).filter_by(warehouse_id=wid).count(); c1,c2=st.columns(2)
            if c1.button('Desactivar'): w.active=False; w.updated_at=now(); s.commit(); audit('warehouses',wid,'DEACTIVATE',w.name); st.success('Desactivada.')
            if moves: c2.warning('No se puede eliminar porque tiene movimientos.')
            elif c2.button('Eliminar físicamente'): s.delete(w); s.commit(); audit('warehouses',wid,'DELETE','Eliminada'); st.success('Eliminada.')
        s.close()
elif menu=='Bloques':
    require_perm('blocks.view'); tabs=st.tabs(['Consultar','Crear / editar','Desactivar'])
    with tabs[0]:
        s=db(); rows=s.query(Block).order_by(Block.number,Block.code).all(); s.close()
        st.dataframe(pd.DataFrame([{'ID':b.id,'Número':b.number,'Bloque':b.code,'Activo':'Sí' if b.active else 'No'} for b in rows]),width='stretch')
    with tabs[1]:
        require_perm('blocks.manage'); s=db(); blocks=s.query(Block).order_by(Block.number,Block.code).all(); s.close(); mode=st.radio('Modo',['Crear nuevo','Editar existente'],horizontal=True)
        if mode=='Crear nuevo':
            with st.form('new_block'):
                c1,c2=st.columns(2); num=c1.number_input('Número',min_value=1,value=1,step=1); code=c2.text_input('Código de bloque')
                if st.form_submit_button('Crear bloque'):
                    s=db(); b=Block(number=int(num),code=code.strip(),active=True); s.add(b)
                    try: s.commit(); audit('blocks',b.id,'CREATE',b.code); st.success('Bloque creado.')
                    except IntegrityError: s.rollback(); st.error('El código de bloque ya existe.')
                    finally: s.close()
        elif blocks:
            sel=st.selectbox('Bloque',[f'{b.id} | {b.number} - {b.code}' for b in blocks]); bid=int(sel.split(' | ')[0]); s=db(); b=s.get(Block,bid)
            with st.form('edit_block'):
                c1,c2=st.columns(2); num=c1.number_input('Número',min_value=1,value=int(b.number),step=1); code=c2.text_input('Código',b.code); active=st.checkbox('Activo',b.active)
                if st.form_submit_button('Guardar'):
                    b.number=int(num); b.code=code.strip(); b.active=active; b.updated_at=now()
                    try: s.commit(); audit('blocks',bid,'UPDATE',b.code); st.success('Bloque actualizado.')
                    except IntegrityError: s.rollback(); st.error('Ya existe otro bloque con ese código.')
            s.close()
    with tabs[2]:
        require_perm('blocks.manage'); s=db(); blocks=s.query(Block).order_by(Block.number,Block.code).all(); sel=st.selectbox('Bloque',[f'{b.id} | {b.number} - {b.code}' for b in blocks],key='del_block') if blocks else None
        if sel:
            bid=int(sel.split(' | ')[0]); b=s.get(Block,bid)
            used=s.query(StockMove).filter_by(block_id=bid).count()+s.query(Asset).filter_by(block_id=bid).count()
            c1,c2=st.columns(2)
            if c1.button('Desactivar'): b.active=False; b.updated_at=now(); s.commit(); audit('blocks',bid,'DEACTIVATE',b.code); st.success('Bloque desactivado.')
            if used: c2.warning('No se puede eliminar físicamente porque tiene movimientos o activos.')
            elif c2.button('Eliminar físicamente'): s.delete(b); s.commit(); audit('blocks',bid,'DELETE','Eliminado'); st.success('Bloque eliminado.')
        s.close()
elif menu=='Movimientos Kardex':
    require_perm('moves.view'); tabs=st.tabs(['Consultar','Crear','Editar','Anular','Documentos'])
    with tabs[0]:
        s=db(); rows=s.query(StockMove,Item,Warehouse,Block,User).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).outerjoin(User,StockMove.created_by==User.id).order_by(StockMove.id.desc()).all(); s.close(); acount=attachment_counts('stock_move'); df=pd.DataFrame([{'ID':m.id,'Fecha':m.move_date,'Código':i.sku,'Producto':i.description,'Bodega':w.name,'Bloque':block_label(b),'Tipo':m.move_type,'Cantidad':m.quantity,'Costo unit.':m.unit_cost,'Documento':m.document,'PDF adjuntos':acount.get(m.id,0),'Estado':m.status,'Reversa de':m.reversal_of,'Creado por':u.full_name if u else '','Anulado por ID':m.annulled_by,'Motivo':m.annul_reason} for m,i,w,b,u in rows]); st.dataframe(df,width='stretch'); 
        if not df.empty: st.download_button('Descargar CSV',df.to_csv(index=False).encode('utf-8-sig'),'movimientos.csv','text/csv')
    with tabs[1]:
        require_perm('moves.create'); s=db(); items=s.query(Item).filter_by(active=True).order_by(Item.description).all(); whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
        if items and whs and blocks:
            with st.form('new_move',clear_on_submit=True):
                c1,c2,c3=st.columns(3); d=c1.date_input('Fecha',date.today()); item_sel=c2.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items]); wh_sel=c3.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs])
                c4,c5,c6=st.columns(3); block_sel=c4.selectbox('Bloque',block_options(blocks)); typ=c5.selectbox('Tipo',['Entrada','Salida','Devolución entrada','Devolución salida']); qty=c6.number_input('Cantidad',min_value=0.0001,value=1.0)
                c7,c8=st.columns(2); cost=c7.number_input('Costo unitario',min_value=0.0,value=0.0); doc=c8.text_input('Documento')
                adj=st.file_uploader('Adjuntar PDF de factura / soporte (opcional)',type=['pdf'],key='new_move_pdf')
                notes=st.text_area('Observaciones')
                if st.form_submit_button('Crear'):
                    item_id=int(item_sel.split(' | ')[0]); wh_id=int(wh_sel.split(' | ')[0]); block_id=parse_block_id(block_sel)
                    if block_id is None: st.error('Selecciona un bloque.'); st.stop()
                    if typ in ('Salida','Devolución salida') and qty>current_stock(item_id,wh_id,block_id): st.error(f'Existencia insuficiente en este bloque. Disponible {current_stock(item_id,wh_id,block_id):g}'); st.stop()
                    s=db(); m=StockMove(move_date=d,item_id=item_id,warehouse_id=wh_id,block_id=block_id,move_type=typ,quantity=qty,unit_cost=cost,document=doc.strip(),notes=notes.strip(),created_by=st.session_state['user_id']); s.add(m); s.commit(); mid=m.id; s.close(); save_attachment(adj,'stock_move',mid); audit('stock_moves',mid,'CREATE',f'{typ} {qty}'); st.success('Movimiento creado.')
        else: st.warning('Crea primero productos, bodegas y bloques activos.')
    with tabs[2]:
        require_perm('moves.edit'); s=db(); rows=s.query(StockMove,Item,Warehouse).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None)).order_by(StockMove.id.desc()).all(); items=s.query(Item).filter_by(active=True).order_by(Item.description).all(); whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
        if rows and blocks:
            sel=st.selectbox('Movimiento',[f'{m.id} | {m.move_date} | {i.sku} - {i.description} | {w.name} | {m.move_type} {m.quantity}' for m,i,w in rows]); mid=int(sel.split(' | ')[0]); s=db(); m=s.get(StockMove,mid)
            item_opts=[f'{i.id} | {i.sku} - {i.description}' for i in items]; wh_opts=[f'{w.id} | {w.name}' for w in whs]; block_opts=block_options(blocks,include_empty=True); di=next((x for x in item_opts if x.startswith(f'{m.item_id} |')),item_opts[0]); dw=next((x for x in wh_opts if x.startswith(f'{m.warehouse_id} |')),wh_opts[0]); dblo=default_block_option(blocks,m.block_id,include_empty=True)
            with st.form('edit_move'):
                c1,c2,c3=st.columns(3); d=c1.date_input('Fecha',m.move_date); item_sel=c2.selectbox('Producto',item_opts,index=item_opts.index(di)); wh_sel=c3.selectbox('Bodega',wh_opts,index=wh_opts.index(dw)); c4,c5,c6=st.columns(3); block_sel=c4.selectbox('Bloque',block_opts,index=block_opts.index(dblo)); types=['Entrada','Salida','Devolución entrada','Devolución salida']; typ=c5.selectbox('Tipo',types,index=types.index(m.move_type)); qty=c6.number_input('Cantidad',min_value=0.0001,value=float(m.quantity)); c7,c8=st.columns(2); cost=c7.number_input('Costo unitario',min_value=0.0,value=float(m.unit_cost)); doc=c8.text_input('Documento',m.document or ''); notes=st.text_area('Observaciones',m.notes or '')
                if st.form_submit_button('Guardar'):
                    item_id=int(item_sel.split(' | ')[0]); wh_id=int(wh_sel.split(' | ')[0]); block_id=parse_block_id(block_sel)
                    if block_id is None: st.error('Selecciona un bloque.'); st.stop()
                    if typ in ('Salida','Devolución salida') and qty>current_stock(item_id,wh_id,block_id,exclude=mid): st.error(f'Existencia insuficiente sin este movimiento en este bloque: {current_stock(item_id,wh_id,block_id,exclude=mid):g}'); st.stop()
                    m.move_date=d; m.item_id=item_id; m.warehouse_id=wh_id; m.block_id=block_id; m.move_type=typ; m.quantity=qty; m.unit_cost=cost; m.document=doc.strip(); m.notes=notes.strip(); m.updated_at=now(); m.updated_by=st.session_state['user_id']; s.commit(); audit('stock_moves',mid,'UPDATE',f'{typ} {qty}'); st.success('Actualizado.')
            s.close()
    with tabs[3]:
        require_perm('moves.annul'); s=db(); rows=s.query(StockMove,Item,Warehouse,Block).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None)).order_by(StockMove.id.desc()).all(); s.close()
        if rows:
            sel=st.selectbox('Movimiento a anular',[f'{m.id} | {m.move_date} | {i.sku} - {i.description} | {w.name} | {block_label(b)} | {m.move_type} {m.quantity}' for m,i,w,b in rows]); mid=int(sel.split(' | ')[0]); reason=st.text_area('Motivo de anulación')
            if st.button('Anular con reversa'):
                if not reason.strip(): st.error('Indica el motivo.'); st.stop()
                s=db(); m=s.get(StockMove,mid); revtype={'Entrada':'Salida','Salida':'Entrada','Devolución entrada':'Salida','Devolución salida':'Entrada'}[m.move_type]
                if m.move_type in ('Entrada','Devolución entrada') and m.quantity>current_stock(m.item_id,m.warehouse_id,m.block_id): st.error('No se puede anular esta entrada porque ya fue consumida parcial o totalmente. Primero revierte las salidas relacionadas.'); st.stop()
                m.status='Anulado'; m.annulled_by=st.session_state['user_id']; m.annulled_at=now(); m.annul_reason=reason.strip(); m.updated_at=now(); m.updated_by=st.session_state['user_id']; rev=StockMove(move_date=date.today(),item_id=m.item_id,warehouse_id=m.warehouse_id,block_id=m.block_id,move_type=revtype,quantity=m.quantity,unit_cost=m.unit_cost,document=m.document,notes=f'Reversa automática del movimiento {m.id}. Motivo: {reason.strip()}',status='Reversa',reversal_of=m.id,created_by=st.session_state['user_id']); s.add(rev); s.commit(); rid=rev.id; s.close(); audit('stock_moves',mid,'ANNUL',reason); audit('stock_moves',rid,'CREATE_REVERSAL',f'Reversa {mid}'); st.success(f'Anulado correctamente. Registro de reversa creado solo para trazabilidad: {rid}')
    with tabs[4]:
        attachments_download_panel('stock_move','Documentos adjuntos de movimientos')
elif menu=='Existencias':
    require_perm('moves.view'); inv=inventory_df(); view=inv.drop(columns=[c for c in ['item_id','warehouse_id','block_id'] if c in inv.columns])
    show_filterable_table(view,'existencias_filterable')
    if not view.empty: st.download_button('Descargar existencias',view.to_csv(index=False).encode('utf-8-sig'),'existencias.csv','text/csv')
elif menu=='Activos fijos':
    require_perm('assets.view'); tabs=st.tabs(['Consultar','Crear','Editar','Baja / reactivar / eliminar','Documentos'])
    with tabs[0]:
        s=db(); rows=s.query(Asset,Block).outerjoin(Block,Asset.block_id==Block.id).order_by(Asset.id.desc()).all(); s.close(); acount=attachment_counts('asset'); df=pd.DataFrame([{'ID':a.id,'Código':a.asset_code,'Descripción':a.description,'Bloque':block_label(b),'Categoría':a.category,'Adquisición':a.acquisition_date,'Puesta en uso':a.in_service_date,'Costo':a.acquisition_cost,'Residual':a.residual_value,'Responsable':a.responsible,'Ubicación':a.location,'Proveedor':a.supplier,'Documento':a.document,'PDF adjuntos':acount.get(a.id,0),'Estado':a.status,'Activo':'Sí' if a.active else 'No'} for a,b in rows]); st.dataframe(df,width='stretch'); 
        if not df.empty: st.download_button('Descargar activos',df.to_csv(index=False).encode('utf-8-sig'),'activos_fijos.csv','text/csv')
    with tabs[1]:
        require_perm('assets.create'); s=db(); rules=s.query(DepRule).filter_by(active=True).order_by(DepRule.category).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
        if rules and blocks:
            with st.form('new_asset',clear_on_submit=True):
                c1,c2,c3=st.columns(3); code=c1.text_input('Código activo'); desc=c2.text_input('Descripción'); block_sel=c3.selectbox('Bloque',block_options(blocks)); c4,c5,c6=st.columns(3); cat=c4.selectbox('Categoría',[r.category for r in rules]); acq=c5.date_input('Fecha adquisición',date.today()); serv=c6.date_input('Fecha puesta en uso',date.today()); c7,c8,c9=st.columns(3); cost=c7.number_input('Costo',min_value=0.0,value=0.0); res=c8.number_input('Valor residual',min_value=0.0,value=0.0); resp=c9.text_input('Responsable'); c10,c11,c12=st.columns(3); loc=c10.text_input('Ubicación'); supp=c11.text_input('Proveedor'); doc=c12.text_input('Documento'); adj=st.file_uploader('Adjuntar PDF de factura / soporte del activo (opcional)',type=['pdf'],key='new_asset_pdf'); notes=st.text_area('Observaciones')
                if st.form_submit_button('Crear activo'):
                    if res>cost or serv<acq: st.error('Revisa residual/fechas.'); st.stop()
                    block_id=parse_block_id(block_sel)
                    if block_id is None: st.error('Selecciona un bloque.'); st.stop()
                    s=db(); a=Asset(asset_code=code.strip(),description=desc.strip(),block_id=block_id,category=cat,acquisition_date=acq,in_service_date=serv,acquisition_cost=cost,residual_value=res,responsible=resp.strip(),location=loc.strip(),supplier=supp.strip(),document=doc.strip(),notes=notes.strip(),created_by=st.session_state['user_id']); s.add(a)
                    try: s.commit(); aid=a.id; save_attachment(adj,'asset',aid); audit('assets',aid,'CREATE',a.asset_code); st.success('Activo creado.')
                    except IntegrityError: s.rollback(); st.error('Código duplicado.')
                    finally: s.close()
    with tabs[2]:
        require_perm('assets.edit'); s=db(); assets=s.query(Asset).order_by(Asset.id.desc()).all(); rules=s.query(DepRule).filter_by(active=True).order_by(DepRule.category).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
        if assets and rules and blocks:
            sel=st.selectbox('Activo',[f'{a.id} | {a.asset_code} - {a.description}' for a in assets]); aid=int(sel.split(' | ')[0]); s=db(); a=s.get(Asset,aid); cats=[r.category for r in rules]; idx=cats.index(a.category) if a.category in cats else 0; block_opts=block_options(blocks,include_empty=True); dblo=default_block_option(blocks,a.block_id,include_empty=True)
            with st.form('edit_asset'):
                c1,c2,c3=st.columns(3); code=c1.text_input('Código',a.asset_code); desc=c2.text_input('Descripción',a.description); block_sel=c3.selectbox('Bloque',block_opts,index=block_opts.index(dblo)); c4,c5,c6=st.columns(3); cat=c4.selectbox('Categoría',cats,index=idx); acq=c5.date_input('Adquisición',a.acquisition_date); serv=c6.date_input('Puesta en uso',a.in_service_date); c7,c8,c9=st.columns(3); cost=c7.number_input('Costo',min_value=0.0,value=float(a.acquisition_cost)); res=c8.number_input('Residual',min_value=0.0,value=float(a.residual_value or 0)); resp=c9.text_input('Responsable',a.responsible or ''); c10,c11,c12=st.columns(3); loc=c10.text_input('Ubicación',a.location or ''); supp=c11.text_input('Proveedor',a.supplier or ''); doc=c12.text_input('Documento',a.document or ''); status=st.selectbox('Estado',['Activo','Baja','Vendido','Dañado','Extraviado'],index=['Activo','Baja','Vendido','Dañado','Extraviado'].index(a.status) if a.status in ['Activo','Baja','Vendido','Dañado','Extraviado'] else 0); active=st.checkbox('Activo en sistema',a.active); notes=st.text_area('Observaciones',a.notes or '')
                if st.form_submit_button('Guardar'):
                    if res>cost or serv<acq: st.error('Revisa residual/fechas.'); st.stop()
                    block_id=parse_block_id(block_sel)
                    if block_id is None: st.error('Selecciona un bloque.'); st.stop()
                    a.asset_code=code.strip(); a.description=desc.strip(); a.block_id=block_id; a.category=cat; a.acquisition_date=acq; a.in_service_date=serv; a.acquisition_cost=cost; a.residual_value=res; a.responsible=resp.strip(); a.location=loc.strip(); a.supplier=supp.strip(); a.document=doc.strip(); a.status=status; a.active=active; a.notes=notes.strip(); a.updated_at=now(); a.updated_by=st.session_state['user_id']
                    try: s.commit(); audit('assets',aid,'UPDATE',a.asset_code); st.success('Activo actualizado.')
                    except IntegrityError: s.rollback(); st.error('Código duplicado.')
            s.close()
    with tabs[3]:
        require_perm('assets.delete'); s=db(); assets=s.query(Asset).order_by(Asset.id.desc()).all(); sel=st.selectbox('Activo',[f'{a.id} | {a.asset_code} - {a.description} | {a.status}' for a in assets],key='asset_del') if assets else None
        if sel:
            aid=int(sel.split(' | ')[0]); a=s.get(Asset,aid); c1,c2,c3=st.columns(3)
            if c1.button('Dar de baja'): a.status='Baja'; a.active=False; a.updated_at=now(); s.commit(); audit('assets',aid,'DEACTIVATE',a.asset_code); st.success('Dado de baja.')
            if c2.button('Reactivar'): a.status='Activo'; a.active=True; a.updated_at=now(); s.commit(); audit('assets',aid,'REACTIVATE',a.asset_code); st.success('Reactivado.')
            if c3.button('Eliminar físicamente'): s.delete(a); s.commit(); audit('assets',aid,'DELETE','Eliminado'); st.success('Eliminado.')
        s.close()
    with tabs[4]:
        attachments_download_panel('asset','Documentos adjuntos de activos fijos')
elif menu=='Depreciación':
    require_perm('assets.view')
    s=db()
    assets=s.query(Asset).filter_by(active=True).order_by(Asset.asset_code).all()
    rules=s.query(DepRule).filter_by(active=True).all()
    s.close()
    rmap={r.category:r for r in rules}

    if not rules:
        st.warning('No hay reglas de depreciación activas. Ve a "Reglas depreciación" y crea o reactiva una regla.')
    elif not assets:
        st.info('No hay activos fijos activos registrados todavía. Primero registra un activo en "Activos fijos".')
    else:
        sel=st.selectbox('Activo',[f'{a.id} | {a.asset_code} - {a.description}' for a in assets])
        aid=int(sel.split(' | ')[0])
        a=[x for x in assets if x.id==aid][0]
        r=rmap.get(a.category)
        if r:
            st.write(f'**Categoría:** {a.category} | **Tasa anual:** {r.annual_rate*100:.2f}% | **Vida útil:** {r.useful_life_years:g} años')
            df=dep_schedule(a,r.annual_rate)
            st.dataframe(df,width='stretch')
            if df.empty:
                st.info('Este activo aún no genera depreciación con las fechas registradas.')
            else:
                c1,c2,c3=st.columns(3)
                c1.metric('Costo',f'${a.acquisition_cost:,.2f}')
                c2.metric('Dep. acumulada',f"${df.iloc[-1]['Dep. acumulada']:,.2f}")
                c3.metric('Valor libros',f"${df.iloc[-1]['Valor en libros']:,.2f}")
                st.download_button('Descargar cálculo',df.to_csv(index=False).encode('utf-8-sig'),f'depreciacion_{a.asset_code}.csv','text/csv')
        else:
            st.error('No hay regla activa para la categoría de este activo. Revisa "Reglas depreciación".')
elif menu=='Reglas depreciación':
    require_perm('deprules.view'); tabs=st.tabs(['Consultar','Crear / editar','Desactivar / eliminar'])
    with tabs[0]:
        s=db(); rows=s.query(DepRule).order_by(DepRule.category).all(); s.close(); st.dataframe(pd.DataFrame([{'ID':r.id,'Categoría':r.category,'Tasa anual %':r.annual_rate*100,'Vida útil años':r.useful_life_years,'Activa':'Sí' if r.active else 'No'} for r in rows]),width='stretch')
    with tabs[1]:
        require_perm('deprules.manage'); s=db(); rules=s.query(DepRule).order_by(DepRule.category).all(); s.close(); mode=st.radio('Modo',['Crear nueva','Editar existente'],horizontal=True)
        if mode=='Crear nueva':
            with st.form('new_rule'):
                c1,c2,c3=st.columns(3); cat=c1.text_input('Categoría'); rate=c2.number_input('Tasa anual %',min_value=0.01,max_value=100.0,value=20.0); life=c3.number_input('Vida útil años',min_value=0.1,value=5.0)
                if st.form_submit_button('Crear'):
                    s=db(); r=DepRule(category=cat.strip(),annual_rate=rate/100,useful_life_years=life,created_by=st.session_state['user_id']); s.add(r)
                    try: s.commit(); audit('depreciation_rules',r.id,'CREATE',r.category); st.success('Regla creada.')
                    except IntegrityError: s.rollback(); st.error('Categoría duplicada.')
                    finally: s.close()
        elif rules:
            sel=st.selectbox('Regla',[f'{r.id} | {r.category}' for r in rules]); rid=int(sel.split(' | ')[0]); s=db(); r=s.get(DepRule,rid)
            with st.form('edit_rule'):
                c1,c2,c3=st.columns(3); cat=c1.text_input('Categoría',r.category); rate=c2.number_input('Tasa anual %',min_value=0.01,max_value=100.0,value=float(r.annual_rate*100)); life=c3.number_input('Vida útil años',min_value=0.1,value=float(r.useful_life_years)); active=st.checkbox('Activa',r.active)
                if st.form_submit_button('Guardar'): r.category=cat.strip(); r.annual_rate=rate/100; r.useful_life_years=life; r.active=active; r.updated_at=now(); s.commit(); audit('depreciation_rules',rid,'UPDATE',r.category); st.success('Regla actualizada.')
            s.close()
    with tabs[2]:
        require_perm('deprules.manage'); s=db(); rules=s.query(DepRule).order_by(DepRule.category).all(); sel=st.selectbox('Regla',[f'{r.id} | {r.category}' for r in rules],key='del_rule') if rules else None
        if sel:
            rid=int(sel.split(' | ')[0]); r=s.get(DepRule,rid); used=s.query(Asset).filter_by(category=r.category).count(); c1,c2=st.columns(2)
            if c1.button('Desactivar'): r.active=False; r.updated_at=now(); s.commit(); audit('depreciation_rules',rid,'DEACTIVATE',r.category); st.success('Desactivada.')
            if used: c2.warning('No puede eliminarse porque hay activos en esa categoría.')
            elif c2.button('Eliminar físicamente'): s.delete(r); s.commit(); audit('depreciation_rules',rid,'DELETE','Eliminada'); st.success('Eliminada.')
        s.close()
elif menu=='Usuarios y roles':
    require_perm('users.manage'); tabs=st.tabs(['Usuarios','Crear usuario','Editar usuario','Roles y permisos'])
    with tabs[0]:
        s=db(); rows=s.query(User,Role).select_from(User).join(Role,User.role_id==Role.id).order_by(User.username).all(); s.close(); st.dataframe(pd.DataFrame([{'ID':u.id,'Usuario':u.username,'Nombre':u.full_name,'Rol':r.name,'Activo':'Sí' if u.active else 'No','Cambio clave':'Sí' if u.must_change_password else 'No'} for u,r in rows]),width='stretch')
    with tabs[1]:
        s=db(); roles=s.query(Role).filter_by(active=True).order_by(Role.name).all(); s.close()
        with st.form('new_user'):
            c1,c2,c3=st.columns(3); uname=c1.text_input('Usuario'); fullname=c2.text_input('Nombre'); role_sel=c3.selectbox('Rol',[f'{r.id} | {r.name}' for r in roles]); pwd=st.text_input('Contraseña temporal',type='password')
            if st.form_submit_button('Crear'):
                if len(pwd)<8: st.error('Mínimo 8 caracteres.'); st.stop()
                salt,h=hash_password(pwd); s=db(); u=User(username=uname.strip(),full_name=fullname.strip(),password_salt=salt,password_hash=h,role_id=int(role_sel.split(' | ')[0]),active=True,must_change_password=True); s.add(u)
                try: s.commit(); audit('users',u.id,'CREATE',u.username); st.success('Usuario creado.')
                except IntegrityError: s.rollback(); st.error('Usuario duplicado.')
                finally: s.close()
    with tabs[2]:
        s=db(); users=s.query(User).order_by(User.username).all(); roles=s.query(Role).filter_by(active=True).order_by(Role.name).all(); s.close()
        if users:
            sel=st.selectbox('Usuario',[f'{u.id} | {u.username} - {u.full_name}' for u in users]); uid=int(sel.split(' | ')[0]); s=db(); u=s.get(User,uid); role_opts=[f'{r.id} | {r.name}' for r in roles]; dr=next((x for x in role_opts if x.startswith(f'{u.role_id} |')),role_opts[0])
            with st.form('edit_user'):
                c1,c2,c3=st.columns(3); uname=c1.text_input('Usuario',u.username); fullname=c2.text_input('Nombre',u.full_name); role_sel=c3.selectbox('Rol',role_opts,index=role_opts.index(dr)); active=st.checkbox('Activo',u.active); pwd=st.text_input('Nueva contraseña opcional',type='password'); force=st.checkbox('Forzar cambio contraseña',u.must_change_password)
                if st.form_submit_button('Guardar'):
                    u.username=uname.strip(); u.full_name=fullname.strip(); u.role_id=int(role_sel.split(' | ')[0]); u.active=active; u.must_change_password=force; u.updated_at=now()
                    if pwd:
                        if len(pwd)<8: st.error('Mínimo 8 caracteres.'); st.stop()
                        salt,h=hash_password(pwd); u.password_salt=salt; u.password_hash=h; u.must_change_password=True
                    try: s.commit(); audit('users',uid,'UPDATE',u.username); st.success('Usuario actualizado.')
                    except IntegrityError: s.rollback(); st.error('Usuario duplicado.')
            s.close()
    with tabs[3]:
        s=db(); roles=s.query(Role).order_by(Role.name).all(); perms=s.query(Permission).order_by(Permission.code).all(); sel=st.selectbox('Rol',[f'{r.id} | {r.name}' for r in roles]); rid=int(sel.split(' | ')[0]); assigned={rp.permission_id for rp in s.query(RolePermission).filter_by(role_id=rid).all()}; chosen=[]
        for p in perms:
            if st.checkbox(f'{p.code} — {p.description}', value=p.id in assigned, key=f'perm_{rid}_{p.id}'): chosen.append(p.id)
        if st.button('Guardar permisos'): s.query(RolePermission).filter_by(role_id=rid).delete(); [s.add(RolePermission(role_id=rid,permission_id=pid)) for pid in chosen]; s.commit(); audit('roles',rid,'UPDATE_PERMISSIONS','Permisos actualizados'); st.success('Permisos actualizados.')
        s.close()
elif menu=='Respaldos':
    require_perm('backup.manage'); st.write('Respaldo automático diario y manual descargable.');
    if st.button('Crear respaldo ahora'): p=export_backup('manual'); audit('backup_log',0,'CREATE_BACKUP',p.name); st.success(f'Respaldo creado: {p.name}')
    s=db(); logs=s.query(BackupLog).order_by(BackupLog.id.desc()).limit(50).all(); s.close(); st.dataframe(pd.DataFrame([{'ID':b.id,'Archivo':b.file_name,'Tipo':b.backup_type,'Fecha':b.created_at} for b in logs]),width='stretch')
    files=sorted(BACKUP_DIR.glob('*.zip'),reverse=True)
    if files:
        sel=st.selectbox('Archivo',[f.name for f in files]); p=BACKUP_DIR/sel; st.download_button('Descargar ZIP',p.read_bytes(),sel,'application/zip')
elif menu=='Bitácora':
    require_perm('audit.view'); s=db(); rows=s.query(AuditLog,User).outerjoin(User,AuditLog.user_id==User.id).order_by(AuditLog.id.desc()).limit(2000).all(); s.close(); df=pd.DataFrame([{'ID':a.id,'Tabla':a.table_name,'Registro':a.record_id,'Acción':a.action,'Detalle':a.detail,'Usuario':u.full_name if u else '','Fecha':a.created_at} for a,u in rows]); st.dataframe(df,width='stretch'); 
    if not df.empty: st.download_button('Descargar bitácora',df.to_csv(index=False).encode('utf-8-sig'),'bitacora.csv','text/csv')
