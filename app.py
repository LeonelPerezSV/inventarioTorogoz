
import os, io, csv, zipfile, hashlib, secrets
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, LargeBinary, inspect as sa_inspect, text as sa_text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError
from consumos import (CAMPOS, is_outbound, validate_classification, render_classification, describe_classification)
from traslados import create_transfer, annul_transfer, MOVE_OUT, MOVE_IN
from comprobantes import generar_comprobante, folio_movimiento, nombre_comprobante
from comprobantes_requisicion import pdf_requisicion, pdf_salida
from requisiciones import create_request, prepare_delivery, issue_delivery, cancel_delivery, cancel_request, remaining_lines

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
    __tablename__='stock_moves'; id=Column(Integer, primary_key=True); move_date=Column(Date, nullable=False); item_id=Column(Integer, ForeignKey('items.id'), nullable=False); warehouse_id=Column(Integer, ForeignKey('warehouses.id'), nullable=False); block_id=Column(Integer, ForeignKey('blocks.id')); consumption_type=Column(String(80)); consumption_detail=Column(String(140)); consumption_lot=Column(String(10)); consumption_sector=Column(String(10)); consumption_subsector=Column(String(12)); move_type=Column(String(40), nullable=False); quantity=Column(Float, nullable=False); unit_cost=Column(Float, default=0); document=Column(String(180)); notes=Column(Text); delivered_by=Column(String(160)); received_by=Column(String(160)); status=Column(String(40), default='Registrado'); reversal_of=Column(Integer, ForeignKey('stock_moves.id')); annulled_by=Column(Integer, ForeignKey('users.id')); annulled_at=Column(DateTime); annul_reason=Column(Text); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id')); item=relationship('Item'); warehouse=relationship('Warehouse'); block=relationship('Block')
class WarehouseTransfer(Base):
    __tablename__='warehouse_transfers'
    id=Column(Integer,primary_key=True)
    move_date=Column(Date,nullable=False)
    item_id=Column(Integer,ForeignKey('items.id'),nullable=False)
    from_warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False)
    to_warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False)
    block_id=Column(Integer,ForeignKey('blocks.id'),nullable=False)
    quantity=Column(Float,nullable=False)
    unit_cost=Column(Float,default=0)
    document=Column(String(180))
    notes=Column(Text)
    delivered_by=Column(String(160))
    received_by=Column(String(160))
    status=Column(String(40),default='Registrado',nullable=False)
    out_move_id=Column(Integer,ForeignKey('stock_moves.id'))
    in_move_id=Column(Integer,ForeignKey('stock_moves.id'))
    created_at=Column(DateTime,default=now)
    created_by=Column(Integer,ForeignKey('users.id'))
    annulled_by=Column(Integer,ForeignKey('users.id'))
    annulled_at=Column(DateTime)
    annul_reason=Column(Text)


class MaterialRequest(Base):
    __tablename__='material_requests'
    id=Column(Integer,primary_key=True)
    request_date=Column(Date,nullable=False)
    requested_by=Column(Integer,ForeignKey('users.id'),nullable=False)
    requested_for=Column(String(180))
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'),nullable=False)
    block_id=Column(Integer,ForeignKey('blocks.id'),nullable=False)
    consumption_type=Column(String(80))
    consumption_detail=Column(String(140))
    consumption_lot=Column(String(10))
    consumption_sector=Column(String(10))
    consumption_subsector=Column(String(12))
    notes=Column(Text)
    status=Column(String(25),nullable=False,default='Pendiente')
    created_at=Column(DateTime,default=now,nullable=False)
    cancelled_by=Column(Integer,ForeignKey('users.id'))
    cancelled_at=Column(DateTime)
    cancel_reason=Column(Text)

class MaterialRequestLine(Base):
    __tablename__='material_request_lines'
    id=Column(Integer,primary_key=True)
    request_id=Column(Integer,ForeignKey('material_requests.id'),nullable=False)
    item_id=Column(Integer,ForeignKey('items.id'),nullable=False)
    quantity=Column(Float,nullable=False)

class MaterialDelivery(Base):
    __tablename__='material_deliveries'
    id=Column(Integer,primary_key=True)
    request_id=Column(Integer,ForeignKey('material_requests.id'),nullable=False)
    dispatch_date=Column(Date,nullable=False)
    status=Column(String(25),nullable=False,default='Preparada')
    prepared_by=Column(Integer,ForeignKey('users.id'),nullable=False)
    delivered_by=Column(String(160),nullable=False)
    received_by=Column(String(160),nullable=False)
    notes=Column(Text)
    created_at=Column(DateTime,default=now,nullable=False)
    issued_by=Column(Integer,ForeignKey('users.id'))
    issued_at=Column(DateTime)
    cancelled_by=Column(Integer,ForeignKey('users.id'))
    cancelled_at=Column(DateTime)
    cancel_reason=Column(Text)

class MaterialDeliveryLine(Base):
    __tablename__='material_delivery_lines'
    id=Column(Integer,primary_key=True)
    dispatch_id=Column(Integer,ForeignKey('material_deliveries.id'),nullable=False)
    request_line_id=Column(Integer,ForeignKey('material_request_lines.id'),nullable=False)
    quantity=Column(Float,nullable=False)
    move_id=Column(Integer,ForeignKey('stock_moves.id'))

class DepRule(Base):
    __tablename__='depreciation_rules'; id=Column(Integer, primary_key=True); category=Column(String(120), unique=True, nullable=False); annual_rate=Column(Float, nullable=False); useful_life_years=Column(Float, nullable=False); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class Asset(Base):
    __tablename__='assets'; id=Column(Integer, primary_key=True); asset_code=Column(String(80), unique=True, nullable=False); description=Column(String(250), nullable=False); category=Column(String(120), nullable=False); acquisition_date=Column(Date, nullable=False); in_service_date=Column(Date, nullable=False); acquisition_cost=Column(Float, nullable=False); residual_value=Column(Float, default=0); responsible=Column(String(160)); location=Column(String(160)); supplier=Column(String(180)); document=Column(String(180)); block_id=Column(Integer, ForeignKey('blocks.id')); status=Column(String(40), default='Activo'); notes=Column(Text); active=Column(Boolean, default=True); created_at=Column(DateTime, default=now); updated_at=Column(DateTime); created_by=Column(Integer, ForeignKey('users.id')); updated_by=Column(Integer, ForeignKey('users.id'))
class AuditLog(Base):
    __tablename__='audit_log'; id=Column(Integer, primary_key=True); table_name=Column(String(80), nullable=False); record_id=Column(Integer, nullable=False); action=Column(String(80), nullable=False); detail=Column(Text); user_id=Column(Integer, ForeignKey('users.id')); created_at=Column(DateTime, default=now)
class BackupLog(Base):
    __tablename__='backup_log'; id=Column(Integer, primary_key=True); file_name=Column(String(240), nullable=False); file_path=Column(Text, nullable=False); backup_type=Column(String(40), nullable=False); user_id=Column(Integer, ForeignKey('users.id')); created_at=Column(DateTime, default=now)

PERMISSIONS={
'dashboard.view':'Ver dashboard','items.view':'Ver productos','items.create':'Crear productos','items.edit':'Editar productos','items.delete':'Desactivar/eliminar productos','warehouses.view':'Ver bodegas','warehouses.create':'Crear bodegas','warehouses.edit':'Editar bodegas','warehouses.delete':'Desactivar/eliminar bodegas','blocks.view':'Ver bloques','blocks.manage':'Administrar bloques','moves.view':'Ver Kardex/movimientos','moves.create':'Crear movimientos','moves.edit':'Editar movimientos','moves.annul':'Anular movimientos','transfers.view':'Consultar traslados','transfers.create':'Registrar traslados entre bodegas','transfers.annul':'Anular traslados entre bodegas','requests.view':'Ver requisiciones','requests.view_all':'Ver requisiciones de otros usuarios','requests.create':'Solicitar materiales','requests.prepare':'Preparar salida de almacén','requests.issue':'Emitir salida de almacén','requests.annul':'Anular requisiciones o salidas','assets.view':'Ver activos fijos','assets.create':'Crear activos fijos','assets.edit':'Editar activos fijos','assets.delete':'Dar de baja/eliminar activos','deprules.view':'Ver reglas depreciación','deprules.manage':'Administrar reglas depreciación','users.manage':'Administrar usuarios/roles','backup.manage':'Respaldos','audit.view':'Bitácora'}
ROLE_PERMISSION_MAP={'Administrador':list(PERMISSIONS.keys()),'Supervisor':['dashboard.view','items.view','items.create','items.edit','warehouses.view','warehouses.create','warehouses.edit','blocks.view','blocks.manage','moves.view','moves.create','moves.edit','moves.annul','transfers.view','transfers.create','transfers.annul','assets.view','assets.create','assets.edit','assets.delete','deprules.view','deprules.manage','backup.manage','audit.view'],'Bodega':['dashboard.view','items.view','warehouses.view','blocks.view','moves.view','moves.create','transfers.view','transfers.create','assets.view'],'Activo fijo':['dashboard.view','blocks.view','transfers.view','assets.view','assets.create','assets.edit','assets.delete','deprules.view','moves.view'],'Consulta':['dashboard.view','items.view','warehouses.view','blocks.view','moves.view','assets.view','deprules.view']}


# Roles preexistentes reciben solamente los permisos necesarios para atender solicitudes.
for _role in ('Administrador','Supervisor'):
    ROLE_PERMISSION_MAP[_role] = list(dict.fromkeys(ROLE_PERMISSION_MAP[_role] + [
        'requests.view','requests.view_all','requests.create',
        'requests.prepare','requests.issue','requests.annul']))
ROLE_PERMISSION_MAP['Bodega'] = list(dict.fromkeys(ROLE_PERMISSION_MAP['Bodega'] + [
    'requests.view','requests.view_all','requests.prepare','requests.issue']))
ROLE_PERMISSION_MAP['Campo'] = [
    'items.view','blocks.view','warehouses.view',
    'requests.view','requests.create'
]

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
        # FIX7: responsables de entrega/recepción, compatibles con registros previos.
        for table in ('stock_moves', 'warehouse_transfers'):
            if insp.has_table(table):
                current_columns=cols(table)
                for field in ('delivered_by','received_by'):
                    if field not in current_columns:
                        con.execute(sa_text(f'ALTER TABLE {table} ADD COLUMN {field} VARCHAR(160)'))
        # FIX5: columnas opcionales de clasificación de consumo, sin afectar registros históricos.
        for field, sql_type in [('consumption_type','VARCHAR(80)'), ('consumption_detail','VARCHAR(140)'), ('consumption_lot','VARCHAR(10)'), ('consumption_sector','VARCHAR(10)'), ('consumption_subsector','VARCHAR(12)')]:
            if field not in cols('stock_moves'):
                con.execute(sa_text(f'ALTER TABLE stock_moves ADD COLUMN {field} {sql_type}'))

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
            else: b.number=num  # No reactivar bloques desactivados por el usuario
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

def move_effect(t,q): return q if t in ('Entrada','Devolución entrada',MOVE_IN) else (-q if t in ('Salida','Devolución salida',MOVE_OUT) else 0)
def current_stock(item_id, wh_id, block_id=None, exclude=None):
    s=db(); q=s.query(StockMove).filter(StockMove.item_id==item_id, StockMove.warehouse_id==wh_id, StockMove.status=='Registrado', StockMove.reversal_of.is_(None))
    q=q.filter(StockMove.block_id==block_id) if block_id is not None else q.filter(StockMove.block_id.is_(None))
    if exclude: q=q.filter(StockMove.id!=exclude)
    total=sum(move_effect(m.move_type,m.quantity) for m in q.all()); s.close(); return total

def inventory_df():
    s=db(); rows=s.query(StockMove,Item,Warehouse,Block).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None)).all(); s.close(); data={}; ent={}
    for m,i,w,b in rows:
        bloque=block_label(b); k=(i.id,w.id,m.block_id,i.sku,i.description,w.name,bloque,i.minimum_stock); data[k]=data.get(k,0)+move_effect(m.move_type,m.quantity); ent.setdefault(k,[0,0])
        if m.move_type in ('Entrada','Devolución entrada',MOVE_IN): ent[k][0]+=m.quantity; ent[k][1]+=m.quantity*m.unit_cost
    out=[]
    for k,stock in data.items():
        item_id,wh_id,block_id,sku,desc,wh,bloque,minimo=k; avg=ent[k][1]/ent[k][0] if ent[k][0] else 0
        out.append({'item_id':item_id,'warehouse_id':wh_id,'block_id':block_id,'Código':sku,'Producto':desc,'Bodega':wh,'Bloque':bloque,'Existencia':round(stock,4),'Costo promedio ref.':round(avg,4),'Valor estimado':round(stock*avg,2),'Stock mínimo':minimo,'Alerta':'Bajo mínimo' if stock<=minimo else ''})
    return pd.DataFrame(out)


def _receipt_move(move_id):
    """Lee un movimiento y prepara un PDF por consulta; no expone credenciales ni datos externos."""
    s=db()
    try:
        m=s.get(StockMove, int(move_id))
        if not m or m.reversal_of is not None or m.move_type in (MOVE_OUT,MOVE_IN):
            raise ValueError('Movimiento no disponible para comprobante individual.')
        item=s.get(Item,m.item_id)
        wh=s.get(Warehouse,m.warehouse_id)
        block=s.get(Block,m.block_id) if m.block_id else None
        creator=s.get(User,m.created_by) if m.created_by else None
        canceller=s.get(User,m.annulled_by) if m.annulled_by else None
        row={
            'kind':m.move_type, 'id':m.id, 'fecha':m.move_date,
            'hora_registro':m.created_at, 'estado':m.status, 'sku':item.sku if item else '',
            'producto':item.description if item else '', 'unidad':item.unit if item else '',
            'cantidad':m.quantity, 'costo':m.unit_cost,
            'bodega_origen':wh.name if wh and m.move_type in ('Salida','Devolución salida') else '',
            'bodega_destino':wh.name if wh and m.move_type in ('Entrada','Devolución entrada') else '',
            'bodega':wh.name if wh else '', 'bloque':block_label(block),
            'documento':m.document, 'observaciones':m.notes,
            'tipo_consumo':m.consumption_type, 'detalle_consumo':m.consumption_detail,
            'lote':m.consumption_lot, 'sector':m.consumption_sector,
            'subsector':m.consumption_subsector,
            'entrega':m.delivered_by,'recibe':m.received_by,
            'registra':creator.full_name if creator else '',
            'motivo_anulacion':m.annul_reason,
            'anulado_por':canceller.full_name if canceller else '',
            'anulado_el':m.annulled_at,
        }
    finally:
        s.close()
    return generar_comprobante(row, logo_path=BASE_DIR/'assets'/'logo_comprobante.png')


def _receipt_transfer(transfer_id):
    s=db()
    try:
        t=s.get(WarehouseTransfer,int(transfer_id))
        if not t: raise ValueError('El traslado ya no existe.')
        item=s.get(Item,t.item_id)
        origin=s.get(Warehouse,t.from_warehouse_id)
        destination=s.get(Warehouse,t.to_warehouse_id)
        block=s.get(Block,t.block_id)
        creator=s.get(User,t.created_by) if t.created_by else None
        canceller=s.get(User,t.annulled_by) if t.annulled_by else None
        row={
            'kind':'Traslado', 'id':t.id, 'fecha':t.move_date,
            'hora_registro':t.created_at,'estado':t.status,
            'sku':item.sku if item else '', 'producto':item.description if item else '',
            'unidad':item.unit if item else '', 'cantidad':t.quantity,'costo':t.unit_cost,
            'bodega_origen':origin.name if origin else '',
            'bodega_destino':destination.name if destination else '',
            'bloque':block_label(block), 'documento':t.document,
            'observaciones':t.notes, 'entrega':t.delivered_by,'recibe':t.received_by,
            'registra':creator.full_name if creator else '', 'motivo_anulacion':t.annul_reason,
            'anulado_por':canceller.full_name if canceller else '', 'anulado_el':t.annulled_at,
        }
    finally:
        s.close()
    return generar_comprobante(row, logo_path=BASE_DIR/'assets'/'logo_comprobante.png')


def download_receipt(kind, record_id, key):
    try:
        if kind=='Traslado':
            data=_receipt_transfer(record_id)
        else:
            data=_receipt_move(record_id)
        st.download_button('📄 Descargar comprobante PDF',
                           data=data,
                           file_name=f'{folio_movimiento(kind,record_id)}.pdf',
                           mime='application/pdf',key=f'{key}_{record_id}')
    except Exception as exc:
        st.error(f'No se pudo generar el comprobante: {exc}')


def _requisition_document(request_id, dispatch_id=None):
    """Instantánea inmutable para el PDF antes de cerrar la sesión SQLAlchemy."""
    s=db()
    try:
        req=s.get(MaterialRequest,int(request_id))
        if not req: raise ValueError('Requisición inexistente.')
        warehouse=s.get(Warehouse,req.warehouse_id)
        block=s.get(Block,req.block_id)
        user=s.get(User,req.requested_by)
        req_lines=s.query(MaterialRequestLine).filter_by(request_id=req.id).order_by(MaterialRequestLine.id).all()
        dispatch=s.get(MaterialDelivery,int(dispatch_id)) if dispatch_id else None
        if dispatch and dispatch.request_id != req.id:
            raise ValueError('La salida no corresponde a la requisición.')
        if dispatch and dispatch.status not in ('Emitida','Anulada'):
            raise ValueError('Solo se pueden imprimir salidas emitidas.')
        delivery_map={}
        if dispatch:
            delivery_map={ln.request_line_id:ln.quantity for ln in s.query(MaterialDeliveryLine).filter_by(dispatch_id=dispatch.id).all()}
        issued=s.get(User,dispatch.issued_by) if dispatch and dispatch.issued_by else None
        data={
            'fecha':dispatch.dispatch_date if dispatch else req.request_date,
            'estado':dispatch.status if dispatch else req.status,
            'requisicion':f'RQ-{req.id:06d}',
            'salida':f'SR-{dispatch.id:06d}' if dispatch else None,
            'bodega':warehouse.name if warehouse else '',
            'bloque':block_label(block),
            'solicitante':user.full_name if user else '',
            'cuadrilla':req.requested_for,
            'tipo_consumo':req.consumption_type,
            'detalle_consumo':req.consumption_detail,
            'lote':req.consumption_lot,
            'sector':req.consumption_sector,
            'subsector':req.consumption_subsector,
            'observaciones':dispatch.notes if dispatch and dispatch.notes else req.notes,
            'entrega':dispatch.delivered_by if dispatch else '',
            'recibe':dispatch.received_by if dispatch else '',
            'registra':issued.full_name if issued else '',
            'lineas':[]
        }
        for ln in req_lines:
            if dispatch and ln.id not in delivery_map: continue
            item=s.get(Item,ln.item_id)
            data['lineas'].append({
                'sku':item.sku if item else str(ln.item_id),
                'producto':item.description if item else 'Producto no disponible',
                'unidad':item.unit if item else '',
                'solicitado':float(ln.quantity),
                'entregado':float(delivery_map.get(ln.id,0))
            })
        return data
    finally:
        s.close()


def _may_view_request(req):
    return bool(has_perm('requests.view_all') or req.requested_by==st.session_state.get('user_id'))


def _request_pdf_button(request_id, key):
    payload=_requisition_document(request_id)
    st.download_button('📄 Descargar requisición PDF',pdf_requisicion(payload,BASE_DIR/'assets'/'logo_comprobante.png'),
        file_name=f'RQ-{request_id:06d}.pdf',mime='application/pdf',key=f'pdf_req_{key}_{request_id}')


def _delivery_pdf_button(delivery_id, key):
    s=db()
    try:
        delivery=s.get(MaterialDelivery,delivery_id)
        if not delivery or delivery.status not in ('Emitida','Anulada'):
            return
        payload_req_id=delivery.request_id
    finally:
        s.close()
    payload=_requisition_document(payload_req_id,delivery_id)
    st.download_button('📄 Descargar salida firmable (PDF)',pdf_salida(payload,BASE_DIR/'assets'/'logo_comprobante.png'),
        file_name=f'SR-{delivery_id:06d}.pdf',mime='application/pdf',key=f'pdf_disp_{key}_{delivery_id}')

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
            for name,cls in {'items':Item,'warehouses':Warehouse,'blocks':Block,'stock_moves':StockMove,'warehouse_transfers':WarehouseTransfer,'material_requests':MaterialRequest,'material_request_lines':MaterialRequestLine,'material_deliveries':MaterialDelivery,'material_delivery_lines':MaterialDeliveryLine,'assets':Asset,'depreciation_rules':DepRule,'users':User,'roles':Role,'audit_log':AuditLog}.items():
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
        st.caption('Acceso exclusivo para personal autorizado.')
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
    for name,perm in [('Dashboard','dashboard.view'),('Productos','items.view'),('Bodegas','warehouses.view'),('Bloques','blocks.view'),('Movimientos Kardex','moves.view'),('Traslados entre bodegas','transfers.view'),('Requisiciones de campo','requests.view'),('Existencias','moves.view'),('Activos fijos','assets.view'),('Depreciación','assets.view'),('Reglas depreciación','deprules.view'),('Usuarios y roles','users.manage'),('Respaldos','backup.manage'),('Bitácora','audit.view')]:
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
        if not has_perm('items.create'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:

            with st.form('new_item',clear_on_submit=True):
                c1,c2,c3,c4=st.columns(4); sku=c1.text_input('Código/SKU'); desc=c2.text_input('Descripción'); unit=c3.text_input('Unidad','Unidad'); minimo=c4.number_input('Stock mínimo',min_value=0.0,value=0.0)
                if st.form_submit_button('Crear'):
                    s=db(); it=Item(sku=sku.strip(),description=desc.strip(),unit=unit.strip() or 'Unidad',minimum_stock=minimo,created_by=st.session_state['user_id']); s.add(it)
                    try: s.commit(); audit('items',it.id,'CREATE',it.sku); st.success('Producto creado.')
                    except IntegrityError: s.rollback(); st.error('Código duplicado.')
                    finally: s.close()
    with tabs[2]:
        if not has_perm('items.edit'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); items=s.query(Item).order_by(Item.description).all(); s.close()
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
        if not has_perm('items.delete'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); items=s.query(Item).order_by(Item.description).all(); sel=st.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items],key='del_item') if items else None
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
        if not has_perm('warehouses.create'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:

            with st.form('new_wh',clear_on_submit=True):
                name=st.text_input('Nombre'); desc=st.text_area('Descripción')
                if st.form_submit_button('Crear'):
                    s=db(); w=Warehouse(name=name.strip(),description=desc.strip(),created_by=st.session_state['user_id']); s.add(w)
                    try: s.commit(); audit('warehouses',w.id,'CREATE',w.name); st.success('Bodega creada.')
                    except IntegrityError: s.rollback(); st.error('Bodega duplicada.')
                    finally: s.close()
    with tabs[2]:
        if not has_perm('warehouses.edit'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); whs=s.query(Warehouse).order_by(Warehouse.name).all(); s.close()
            if whs:
                sel=st.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs]); wid=int(sel.split(' | ')[0]); s=db(); w=s.get(Warehouse,wid)
                with st.form('edit_wh'):
                    name=st.text_input('Nombre',w.name); desc=st.text_area('Descripción',w.description or ''); active=st.checkbox('Activa',w.active)
                    if st.form_submit_button('Guardar'): w.name=name.strip(); w.description=desc.strip(); w.active=active; w.updated_at=now(); s.commit(); audit('warehouses',wid,'UPDATE',w.name); st.success('Actualizada.')
                s.close()
    with tabs[3]:
        if not has_perm('warehouses.delete'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); whs=s.query(Warehouse).order_by(Warehouse.name).all(); sel=st.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs],key='del_wh') if whs else None
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
        if not has_perm('blocks.manage'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); blocks=s.query(Block).order_by(Block.number,Block.code).all(); s.close(); mode=st.radio('Modo',['Crear nuevo','Editar existente'],horizontal=True)
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
        if not has_perm('blocks.manage'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); blocks=s.query(Block).order_by(Block.number,Block.code).all(); sel=st.selectbox('Bloque',[f'{b.id} | {b.number} - {b.code}' for b in blocks],key='del_block') if blocks else None
            if sel:
                bid=int(sel.split(' | ')[0]); b=s.get(Block,bid)
                used=s.query(StockMove).filter_by(block_id=bid).count()+s.query(Asset).filter_by(block_id=bid).count()
                c1,c2=st.columns(2)
                if c1.button('Desactivar'): b.active=False; b.updated_at=now(); s.commit(); audit('blocks',bid,'DEACTIVATE',b.code); st.success('Bloque desactivado.')
                if used: c2.warning('No se puede eliminar físicamente porque tiene movimientos o activos.')
                elif c2.button('Eliminar físicamente'): s.delete(b); s.commit(); audit('blocks',bid,'DELETE','Eliminado'); st.success('Bloque eliminado.')
            s.close()
elif menu=='Movimientos Kardex':
    require_perm('moves.view'); tabs=st.tabs(['Consultar','Crear','Editar','Anular','Documentos','Comprobantes PDF'])
    with tabs[0]:
        s=db(); rows=s.query(StockMove,Item,Warehouse,Block,User).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).outerjoin(User,StockMove.created_by==User.id).order_by(StockMove.id.desc()).all(); s.close(); acount=attachment_counts('stock_move'); df=pd.DataFrame([{'ID':m.id,'Fecha':m.move_date,'Código':i.sku,'Producto':i.description,'Bodega':w.name,'Bloque':block_label(b),'Tipo':m.move_type,'Tipo de consumo':m.consumption_type,'Detalle de consumo':m.consumption_detail,'Lote':m.consumption_lot,'Sector':m.consumption_sector,'Subsector':m.consumption_subsector,'Cantidad':m.quantity,'Costo unit.':m.unit_cost,'Documento':m.document,'PDF adjuntos':acount.get(m.id,0),'Estado':m.status,'Reversa de':m.reversal_of,'Creado por':u.full_name if u else '','Anulado por ID':m.annulled_by,'Motivo':m.annul_reason} for m,i,w,b,u in rows]); st.dataframe(df,width='stretch'); 
        if not df.empty: st.download_button('Descargar CSV',df.to_csv(index=False).encode('utf-8-sig'),'movimientos.csv','text/csv')
    with tabs[1]:
        if not has_perm('moves.create'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:

            s=db()
            items=s.query(Item).filter_by(active=True).order_by(Item.description).all()
            whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all()
            blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all()
            s.close()
            if items and whs and blocks:
                # Se renderiza fuera del formulario: Streamlit actualiza inmediatamente
                # los menús dependientes al elegir tipo, sector, etc.
                types=['Entrada','Salida','Devolución entrada','Devolución salida']
                typ=st.selectbox('Movimiento',types,key='create_move_kind')
                classification=render_classification(st,'new_move',typ)
                with st.form('new_move',clear_on_submit=True):
                    c1,c2,c3=st.columns(3)
                    d=c1.date_input('Fecha',date.today())
                    item_sel=c2.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items])
                    wh_sel=c3.selectbox('Bodega',[f'{w.id} | {w.name}' for w in whs])
                    c4,c5,c6=st.columns(3)
                    block_sel=c4.selectbox('Bloque',block_options(blocks))
                    qty=c5.number_input('Cantidad',min_value=0.0001,value=1.0)
                    cost=c6.number_input('Costo unitario',min_value=0.0,value=0.0)
                    doc=st.text_input('Documento')
                    c_e,c_r=st.columns(2)
                    entregado_por=c_e.text_input('Nombre de quien entrega (para el PDF)')
                    recibido_por=c_r.text_input('Nombre de quien recibe (para el PDF)')
                    adj=st.file_uploader('Adjuntar PDF de factura / soporte (opcional)',type=['pdf'],key='new_move_pdf')
                    notes=st.text_area('Observaciones')
                    if st.form_submit_button('Crear'):
                        item_id=int(item_sel.split(' | ')[0])
                        wh_id=int(wh_sel.split(' | ')[0])
                        block_id=parse_block_id(block_sel)
                        if block_id is None:
                            st.error('Selecciona un bloque.')
                            st.stop()
                        try:
                            classification=validate_classification(typ,classification)
                        except ValueError as exc:
                            st.error(str(exc))
                            st.stop()
                        if is_outbound(typ) and qty>current_stock(item_id,wh_id,block_id):
                            st.error(f'Existencia insuficiente en este bloque. Disponible {current_stock(item_id,wh_id,block_id):g}')
                            st.stop()
                        s=db()
                        try:
                            m=StockMove(move_date=d,item_id=item_id,warehouse_id=wh_id,
                                block_id=block_id,move_type=typ,quantity=qty,unit_cost=cost,
                                document=doc.strip(),notes=notes.strip(),
                                delivered_by=entregado_por.strip(),received_by=recibido_por.strip(),
                                created_by=st.session_state['user_id'],**classification)
                            s.add(m)
                            s.commit()
                            mid=m.id
                        finally:
                            s.close()
                        save_attachment(adj,'stock_move',mid)
                        audit('stock_moves',mid,'CREATE',f'{typ} {qty}; {describe_classification(classification)}')
                        st.session_state['last_stock_receipt']=mid
                        st.success('Movimiento guardado. Descarga el comprobante para firmas sin volver a llenar un formulario.')
                if st.session_state.get('last_stock_receipt'):
                    st.caption('Comprobante del último movimiento registrado:')
                    last_mid=st.session_state['last_stock_receipt']
                    s_receipt=db()
                    try:
                        last=s_receipt.get(StockMove,last_mid)
                        last_kind=last.move_type if last else None
                    finally:
                        s_receipt.close()
                    if last_kind:
                        download_receipt(last_kind,last_mid,'kardex_recent_pdf')
            else:
                st.warning('Crea primero productos, bodegas y bloques activos.')
    with tabs[2]:
        if not has_perm('moves.edit'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:

            s=db()
            rows=s.query(StockMove,Item,Warehouse).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None), StockMove.move_type.notin_([MOVE_OUT,MOVE_IN]),~StockMove.id.in_(s.query(MaterialDeliveryLine.move_id).filter(MaterialDeliveryLine.move_id.isnot(None)))).order_by(StockMove.id.desc()).all()
            items=s.query(Item).filter_by(active=True).order_by(Item.description).all()
            whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all()
            blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all()
            s.close()
            if rows and blocks and items and whs:
                sel=st.selectbox('Movimiento',[f'{m.id} | {m.move_date} | {i.sku} - {i.description} | {w.name} | {m.move_type} {m.quantity}' for m,i,w in rows])
                mid=int(sel.split(' | ')[0])
                s=db()
                m=s.get(StockMove,mid)
                item_opts=[f'{i.id} | {i.sku} - {i.description}' for i in items]
                wh_opts=[f'{w.id} | {w.name}' for w in whs]
                block_opts=block_options(blocks,include_empty=True)
                di=next((x for x in item_opts if x.startswith(f'{m.item_id} |')),item_opts[0])
                dw=next((x for x in wh_opts if x.startswith(f'{m.warehouse_id} |')),wh_opts[0])
                dblo=default_block_option(blocks,m.block_id,include_empty=True)
                types=['Entrada','Salida','Devolución entrada','Devolución salida']
                oldvalues={field:getattr(m,field,None) for field in CAMPOS}
                typ=st.selectbox('Movimiento',types,index=types.index(m.move_type),key=f'edit_movement_kind_{mid}')
                classification=render_classification(st,f'edit_move_{mid}',typ,existing=oldvalues)
                with st.form('edit_move'):
                    c1,c2,c3=st.columns(3)
                    d=c1.date_input('Fecha',m.move_date)
                    item_sel=c2.selectbox('Producto',item_opts,index=item_opts.index(di))
                    wh_sel=c3.selectbox('Bodega',wh_opts,index=wh_opts.index(dw))
                    c4,c5,c6=st.columns(3)
                    block_sel=c4.selectbox('Bloque',block_opts,index=block_opts.index(dblo))
                    qty=c5.number_input('Cantidad',min_value=0.0001,value=float(m.quantity))
                    cost=c6.number_input('Costo unitario',min_value=0.0,value=float(m.unit_cost))
                    doc=st.text_input('Documento',m.document or '')
                    c_e,c_r=st.columns(2)
                    entregado_por=c_e.text_input('Quien entrega',m.delivered_by or '')
                    recibido_por=c_r.text_input('Quien recibe',m.received_by or '')
                    notes=st.text_area('Observaciones',m.notes or '')
                    if st.form_submit_button('Guardar'):
                        item_id=int(item_sel.split(' | ')[0]); wh_id=int(wh_sel.split(' | ')[0])
                        block_id=parse_block_id(block_sel)
                        if block_id is None:
                            st.error('Selecciona un bloque.'); st.stop()
                        try:
                            classification=validate_classification(typ,classification)
                        except ValueError as exc:
                            st.error(str(exc)); st.stop()
                        # Validar el saldo del registro destino y también del origen
                        # para impedir que modificar una entrada deje saldos negativos.
                        old_key=(m.item_id,m.warehouse_id,m.block_id)
                        new_key=(item_id,wh_id,block_id)
                        old_before=current_stock(*old_key)
                        old_effect=move_effect(m.move_type,m.quantity)
                        new_effect=move_effect(typ,qty)
                        if old_key==new_key:
                            remaining=old_before-old_effect+new_effect
                            if remaining < -1e-8:
                                st.error('La modificación dejaría el inventario con saldo negativo.'); st.stop()
                        else:
                            remaining_old=old_before-old_effect
                            remaining_new=current_stock(*new_key)+new_effect
                            if min(remaining_old,remaining_new)<-1e-8:
                                st.error('La modificación dejaría saldo negativo en el bloque original o en el nuevo.'); st.stop()
                        m.move_date=d; m.item_id=item_id; m.warehouse_id=wh_id
                        m.block_id=block_id; m.move_type=typ; m.quantity=qty
                        m.unit_cost=cost; m.document=doc.strip(); m.notes=notes.strip()
                        m.delivered_by=entregado_por.strip(); m.received_by=recibido_por.strip()
                        for field,value in classification.items(): setattr(m,field,value)
                        m.updated_at=now(); m.updated_by=st.session_state['user_id']
                        s.commit()
                        audit('stock_moves',mid,'UPDATE',f'{typ} {qty}; {describe_classification(classification)}')
                        st.success('Movimiento actualizado con su clasificación.')
                s.close()
    with tabs[3]:
        if not has_perm('moves.annul'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); rows=s.query(StockMove,Item,Warehouse,Block).select_from(StockMove).join(Item,StockMove.item_id==Item.id).join(Warehouse,StockMove.warehouse_id==Warehouse.id).outerjoin(Block,StockMove.block_id==Block.id).filter(StockMove.status=='Registrado', StockMove.reversal_of.is_(None), StockMove.move_type.notin_([MOVE_OUT,MOVE_IN]),~StockMove.id.in_(s.query(MaterialDeliveryLine.move_id).filter(MaterialDeliveryLine.move_id.isnot(None)))).order_by(StockMove.id.desc()).all(); s.close()
            if rows:
                sel=st.selectbox('Movimiento a anular',[f'{m.id} | {m.move_date} | {i.sku} - {i.description} | {w.name} | {block_label(b)} | {m.move_type} {m.quantity}' for m,i,w,b in rows]); mid=int(sel.split(' | ')[0]); reason=st.text_area('Motivo de anulación')
                if st.button('Anular con reversa'):
                    if not reason.strip(): st.error('Indica el motivo.'); st.stop()
                    s=db(); m=s.get(StockMove,mid); revtype={'Entrada':'Salida','Salida':'Entrada','Devolución entrada':'Salida','Devolución salida':'Entrada'}[m.move_type]
                    if m.move_type in ('Entrada','Devolución entrada') and m.quantity>current_stock(m.item_id,m.warehouse_id,m.block_id): st.error('No se puede anular esta entrada porque ya fue consumida parcial o totalmente. Primero revierte las salidas relacionadas.'); st.stop()
                    m.status='Anulado'; m.annulled_by=st.session_state['user_id']; m.annulled_at=now(); m.annul_reason=reason.strip(); m.updated_at=now(); m.updated_by=st.session_state['user_id']; rev=StockMove(move_date=date.today(),item_id=m.item_id,warehouse_id=m.warehouse_id,block_id=m.block_id,move_type=revtype,quantity=m.quantity,unit_cost=m.unit_cost,document=m.document,notes=f'Reversa automática del movimiento {m.id}. Motivo: {reason.strip()}',status='Reversa',reversal_of=m.id,created_by=st.session_state['user_id'],**{field:getattr(m,field,None) for field in CAMPOS}); s.add(rev); s.commit(); rid=rev.id; s.close(); audit('stock_moves',mid,'ANNUL',reason); audit('stock_moves',rid,'CREATE_REVERSAL',f'Reversa {mid}'); st.success(f'Anulado correctamente. Registro de reversa creado solo para trazabilidad: {rid}')
    with tabs[4]:
        attachments_download_panel('stock_move','Documentos adjuntos de movimientos')
    with tabs[5]:
        st.subheader('Reimprimir comprobantes de Kardex')
        st.caption('Incluye entradas, salidas y devoluciones ya registradas. Los comprobantes anulados indican su estado.')
        s=db()
        try:
            records=s.query(StockMove).filter(StockMove.reversal_of.is_(None),
                StockMove.move_type.in_(['Entrada','Salida','Devolución entrada','Devolución salida'])).order_by(StockMove.id.desc()).limit(1500).all()
            entries=[(m.id,m.move_type,m.move_date,m.status) for m in records]
        finally:
            s.close()
        if entries:
            labels=[f'{folio_movimiento(kind,mid)} | {kind} | {when} | {status}' for mid,kind,when,status in entries]
            selected=st.selectbox('Seleccionar movimiento',labels,key='receipt_stock_choose')
            index=labels.index(selected)
            mid,kind,_,_=entries[index]
            download_receipt(kind,mid,'kardex_history_pdf')
        else:
            st.info('Aún no existen movimientos para generar comprobantes.')
elif menu=='Traslados entre bodegas':
    require_perm('transfers.view')
    tabs=st.tabs(['Historial de traslados','Nuevo traslado','Anular traslado'])
    with tabs[0]:
        s=db()
        try:
            rows=s.query(WarehouseTransfer,Item,Warehouse,Block).select_from(WarehouseTransfer).join(Item,WarehouseTransfer.item_id==Item.id).join(Warehouse,WarehouseTransfer.from_warehouse_id==Warehouse.id).join(Block,WarehouseTransfer.block_id==Block.id).order_by(WarehouseTransfer.id.desc()).all()
            wnames={w.id:w.name for w in s.query(Warehouse).all()}
            usernames={u.id:u.full_name for u in s.query(User).all()}
            df=pd.DataFrame([{'Traslado':f'TR-{t.id:06d}','Fecha':t.move_date,'Código':i.sku,'Producto':i.description,
                'Bodega origen':w.name,'Bodega destino':wnames.get(t.to_warehouse_id,''),'Bloque':block_label(b),
                'Cantidad':t.quantity,'Costo unit. ref.':t.unit_cost,'Referencia':t.document,'Observaciones':t.notes,
                'Estado':t.status,'Registrado por':usernames.get(t.created_by,''),'Anulado por':usernames.get(t.annulled_by,''),
                'Motivo anulación':t.annul_reason} for t,i,w,b in rows])
        finally:
            s.close()
        show_filterable_table(df,'transfer_grid')
        if not df.empty:
            st.download_button('Descargar traslados CSV',df.to_csv(index=False).encode('utf-8-sig'),'traslados.csv','text/csv')
            st.subheader('Comprobante de traslado')
            chosen=st.selectbox('Seleccione traslado para descargar',df['Traslado'].tolist(),key='transfer_receipt_select')
            download_receipt('Traslado',int(chosen.split('-')[-1]),'transfer_history_pdf')
    with tabs[1]:
        if not has_perm('transfers.create'):
            st.info('Tu rol no tiene permiso para registrar traslados.')
        else:
            s=db()
            try:
                items=s.query(Item).filter_by(active=True).order_by(Item.description).all()
                whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all()
                blocks=s.query(Block).filter_by(active=True).order_by(Block.number).all()
            finally:
                s.close()
            if not items or len(whs)<2 or not blocks:
                st.warning('Necesitas un producto, un bloque y al menos dos bodegas activas para hacer un traslado.')
            else:
                with st.form('create_transfer'):
                    c1,c2,c3=st.columns(3)
                    d=c1.date_input('Fecha',date.today(),key='transfer_date')
                    item_sel=c2.selectbox('Producto',[f'{i.id} | {i.sku} - {i.description}' for i in items])
                    block_sel=c3.selectbox('Bloque',block_options(blocks))
                    c4,c5,c6=st.columns(3)
                    wh_options=[f'{w.id} | {w.name}' for w in whs]
                    origin_sel=c4.selectbox('Bodega origen',wh_options)
                    dest_sel=c5.selectbox('Bodega destino',wh_options,index=1)
                    qty=c6.number_input('Cantidad a trasladar',min_value=0.0001,value=1.0)
                    doc=st.text_input('Documento de respaldo (opcional)')
                    c_e,c_r=st.columns(2)
                    entregado_por=c_e.text_input('Nombre de quien entrega (origen)')
                    recibido_por=c_r.text_input('Nombre de quien recibe (destino)')
                    notes=st.text_area('Observaciones')
                    submit=st.form_submit_button('Registrar traslado')
                if submit:
                    item_id=int(item_sel.split(' | ')[0]); origin_id=int(origin_sel.split(' | ')[0]); dest_id=int(dest_sel.split(' | ')[0]); block_id=parse_block_id(block_sel)
                    try:
                        tid,ref=create_transfer(SessionLocal,transfer_cls=WarehouseTransfer,stock_move_cls=StockMove,
                            item_cls=Item,warehouse_cls=Warehouse,block_cls=Block,item_id=item_id,
                            from_warehouse_id=origin_id,to_warehouse_id=dest_id,block_id=block_id,
                            quantity=qty,move_date=d,document=doc.strip(),notes=notes.strip(),
                            delivered_by=entregado_por.strip(),received_by=recibido_por.strip(),
                            user_id=st.session_state['user_id'])
                        audit('warehouse_transfers',tid,'CREATE',f'{ref}: {qty:g} unidades de {origin_sel} a {dest_sel}; bloque {block_sel}')
                        st.session_state['last_transfer_receipt']=tid
                        st.success(f'Traslado {ref} registrado. Origen -{qty:g}; destino +{qty:g}. Descarga el PDF para firmas.')
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f'No se pudo registrar el traslado. No se aplicaron movimientos parciales. Error: {type(exc).__name__}')
                if st.session_state.get('last_transfer_receipt'):
                    st.caption('Comprobante del último traslado registrado:')
                    download_receipt('Traslado',st.session_state['last_transfer_receipt'],'transfer_recent_pdf')
    with tabs[2]:
        if not has_perm('transfers.annul'):
            st.info('Solo un supervisor o administrador puede anular traslados.')
        else:
            s=db()
            try:
                trs=s.query(WarehouseTransfer).filter_by(status='Registrado').order_by(WarehouseTransfer.id.desc()).all()
                labels=[f'{t.id} | TR-{t.id:06d} | {t.quantity:g} unidades | {t.move_date}' for t in trs]
            finally:
                s.close()
            if not trs:
                st.info('No hay traslados pendientes de anulación.')
            else:
                selection=st.selectbox('Traslado',labels)
                tid=int(selection.split(' | ')[0])
                reason=st.text_area('Motivo de anulación')
                if st.button('Anular traslado',type='secondary'):
                    try:
                        annul_transfer(SessionLocal,transfer_cls=WarehouseTransfer,stock_move_cls=StockMove,
                                       item_cls=Item,transfer_id=tid,reason=reason,user_id=st.session_state['user_id'])
                        audit('warehouse_transfers',tid,'ANNUL',reason.strip())
                        st.success('Traslado anulado. Se deshicieron ambos movimientos sin duplicar cantidades.')
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f'No se pudo anular el traslado: {type(exc).__name__}')


elif menu=='Requisiciones de campo':
    require_perm('requests.view')
    tabs=st.tabs(['Consultar / imprimir','Nueva requisición','Preparar salida','Emitir salida e imprimir','Anulaciones','Documentos firmados'])
    with tabs[0]:
        s=db()
        try:
            q=s.query(MaterialRequest).order_by(MaterialRequest.id.desc())
            if not has_perm('requests.view_all'):
                q=q.filter_by(requested_by=st.session_state['user_id'])
            reqs=q.limit(500).all()
            usernames={u.id:u.full_name for u in s.query(User).all()}
            records=[{'ID':r.id,'Folio':f'RQ-{r.id:06d}',
                'Fecha':r.request_date,'Solicitante':usernames.get(r.requested_by,''),
                'Cuadrilla':r.requested_for,'Estado':r.status,
                'Bodega ID':r.warehouse_id,'Bloque ID':r.block_id} for r in reqs]
            deliveries=s.query(MaterialDelivery).order_by(MaterialDelivery.id.desc()).limit(500).all()
            visible_ids={r.id for r in reqs}
            dispatches=[{'ID':x.id,'Salida':f'SR-{x.id:06d}',
                'Requisición':f'RQ-{x.request_id:06d}',
                'Fecha':x.dispatch_date,'Estado':x.status,
                'Entregó':x.delivered_by,'Recibió':x.received_by} for x in deliveries if x.request_id in visible_ids]
        finally:
            s.close()
        st.subheader('Requisiciones')
        show_filterable_table(pd.DataFrame(records),'requests_grid',height=360)
        if reqs:
            chosen=st.selectbox('Reimpresión requisición',
                [f'RQ-{r.id:06d} | {r.status} | {r.request_date}' for r in reqs],key='request_receipt_select')
            rid=int(chosen.split(' | ')[0].split('-')[-1])
            _request_pdf_button(rid,'history')
        st.subheader('Salidas emitidas desde requisiciones')
        show_filterable_table(pd.DataFrame(dispatches),'dispatch_grid',height=330)
        issued=[d for d in deliveries if d.request_id in visible_ids and d.status in ('Emitida','Anulada')]
        if issued:
            chosen=st.selectbox('Reimprimir salida',
                [f'SR-{d.id:06d} | RQ-{d.request_id:06d} | {d.status}' for d in issued],key='delivery_receipt_select')
            did=int(chosen.split(' | ')[0].split('-')[-1])
            _delivery_pdf_button(did,'history')
    with tabs[1]:
        if not has_perm('requests.create'):
            st.info('No tienes permisos para solicitar materiales.')
        else:
            s=db()
            try:
                items=s.query(Item).filter_by(active=True).order_by(Item.description).all()
                whs=s.query(Warehouse).filter_by(active=True).order_by(Warehouse.name).all()
                blocks=s.query(Block).filter_by(active=True).order_by(Block.number).all()
            finally:
                s.close()
            if not items or not whs or not blocks:
                st.info('Primero registra productos, bodegas y bloques.')
            else:
                st.caption('Una requisición no descuenta inventario. Bodega registrará la salida después de preparar los materiales.')
                classification=render_classification(st,'req_new','Salida')
                label_map={f'{i.sku} — {i.description}':i.id for i in items}
                chosen=st.multiselect('Materiales requeridos',list(label_map),key='req_items')
                wanted={}
                for label in chosen:
                    item_id=label_map[label]
                    wanted[item_id]=st.number_input(f'Cantidad solicitada · {label}',
                        min_value=0.001,value=1.0,step=1.0,key=f'req_qty_{item_id}')
                with st.form('new_material_request'):
                    c1,c2=st.columns(2)
                    wh_sel=c1.selectbox('Bodega que atenderá',
                        [f'{w.id} | {w.name}' for w in whs])
                    block_sel=c2.selectbox('Bloque del proyecto',block_options(blocks))
                    destination=st.text_input('Cuadrilla / frente de trabajo / destinatario')
                    notes=st.text_area('Observaciones de requisición')
                    submit=st.form_submit_button('Enviar requisición a bodega')
                if submit:
                    if not wanted:
                        st.error('Selecciona los materiales a solicitar.')
                    else:
                        try:
                            validated=validate_classification('Salida',classification)
                            rid=create_request(SessionLocal,request_cls=MaterialRequest,
                                line_cls=MaterialRequestLine,item_cls=Item,warehouse_cls=Warehouse,
                                block_cls=Block,user_id=st.session_state['user_id'],
                                warehouse_id=int(wh_sel.split(' | ')[0]),block_id=parse_block_id(block_sel),
                                lines=wanted,requested_for=destination,notes=notes,classification=validated)
                            audit('material_requests',rid,'CREATE',f'Requisición RQ-{rid:06d}')
                            st.session_state['new_req_id']=rid
                            st.success(f'Requisición RQ-{rid:06d} creada. Bodega puede prepararla sin descontar existencias todavía.')
                        except ValueError as exc:
                            st.error(str(exc))
                if st.session_state.get('new_req_id'):
                    _request_pdf_button(st.session_state['new_req_id'],'recent')
    with tabs[2]:
        if not has_perm('requests.prepare'):
            st.info('Solo bodega, supervisor o administrador pueden preparar salidas.')
        else:
            s=db()
            try:
                reqs=s.query(MaterialRequest).filter(MaterialRequest.status.in_(['Pendiente','Parcial'])).order_by(MaterialRequest.id.desc()).all()
            finally:
                s.close()
            if not reqs:
                st.info('No hay requisiciones pendientes.')
            else:
                selected=st.selectbox('Requisición para preparar',
                    [f'RQ-{r.id:06d} | {r.status} | {r.requested_for or "Campo"}' for r in reqs],key='prepare_choose')
                rid=int(selected.split(' | ')[0].split('-')[-1])
                s=db()
                try:
                    req=s.get(MaterialRequest,rid)
                    w=s.get(Warehouse,req.warehouse_id);b=s.get(Block,req.block_id)
                    lines=remaining_lines(s,rid,MaterialRequestLine,MaterialDelivery,MaterialDeliveryLine)
                    to_display=[]
                    for ln,remaining in lines:
                        item=s.get(Item,ln.item_id)
                        to_display.append((ln.id,item.sku,item.description,float(remaining),
                            current_stock(ln.item_id,req.warehouse_id,req.block_id)))
                finally:
                    s.close()
                st.caption(f'Bodega: {w.name} | Bloque: {block_label(b)} | Requisición: RQ-{rid:06d}')
                with st.form('material_prepare'):
                    picked={}
                    for lnid,sku,description,remaining,available in to_display:
                        if remaining <= 1e-8: continue
                        st.caption(f'{sku} — {description} | Pendiente: {remaining:g} | Existencia actual: {available:g}')
                        value=st.number_input(f'Cantidad a preparar ({sku})',min_value=0.0,
                            max_value=float(remaining),value=0.0,step=1.0,key=f'prep_{rid}_{lnid}')
                        if value>0: picked[lnid]=value
                    c1,c2=st.columns(2)
                    delivered_by=c1.text_input('Nombre de quien entrega')
                    received_by=c2.text_input('Nombre de quien recibe')
                    notes=st.text_area('Observaciones de preparación')
                    submitted=st.form_submit_button('Guardar preparación (sin descontar stock)')
                if submitted:
                    if not picked: st.error('Selecciona al menos una cantidad mayor que cero.')
                    elif not delivered_by.strip() or not received_by.strip():
                        st.error('Indica quién entrega y quién recibe para el comprobante firmado.')
                    else:
                        try:
                            did=prepare_delivery(SessionLocal,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
                                dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
                                item_cls=Item,stock_move_cls=StockMove,user_id=st.session_state['user_id'],
                                request_id=rid,quantities=picked,delivered_by=delivered_by,received_by=received_by,notes=notes)
                            audit('material_deliveries',did,'PREPARE',f'RQ-{rid:06d}')
                            st.success(f'Preparación SR-{did:06d} guardada. Bodega debe emitir la salida para descontar el Kardex e imprimir.')
                        except ValueError as exc: st.error(str(exc))
    with tabs[3]:
        if not has_perm('requests.issue'):
            st.info('Solo usuarios de bodega autorizados pueden emitir salidas.')
        else:
            s=db()
            try:
                prepared=s.query(MaterialDelivery).filter_by(status='Preparada').order_by(MaterialDelivery.id.desc()).all()
                req_names={r.id:f'RQ-{r.id:06d}' for r in s.query(MaterialRequest).all()}
            finally: s.close()
            if not prepared:
                st.info('No hay preparaciones sin emitir.')
            else:
                selected=st.selectbox('Preparación',
                    [f'SR-{d.id:06d} | {req_names.get(d.request_id, "")} | {d.received_by}' for d in prepared],key='issue_choose')
                did=int(selected.split(' | ')[0].split('-')[-1])
                s=db()
                try:
                    lines=s.query(MaterialDeliveryLine).filter_by(dispatch_id=did).all()
                    summary=[]
                    for dl in lines:
                        rl=s.get(MaterialRequestLine,dl.request_line_id)
                        item=s.get(Item,rl.item_id)
                        summary.append({'Código':item.sku,'Producto':item.description,'A entregar':dl.quantity})
                finally:s.close()
                st.dataframe(pd.DataFrame(summary),width='stretch')
                st.warning('Al confirmar se descontarán inmediatamente las existencias. Después imprime la salida y recoge las firmas físicas.')
                consent=st.checkbox('Confirmo que las cantidades preparadas se entregarán y corresponde emitir la salida.',key=f'confirm_issue_{did}')
                if st.button('Confirmar salida y generar PDF',disabled=not consent,type='primary'):
                    try:
                        issue_delivery(SessionLocal,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
                            dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
                            item_cls=Item,stock_move_cls=StockMove,user_id=st.session_state['user_id'],dispatch_id=did)
                        audit('material_deliveries',did,'ISSUE','Salida emitida y Kardex descontado')
                        st.session_state['last_delivery_id']=did
                        st.success(f'Salida SR-{did:06d} emitida. Imprime el PDF para firmas de quien entrega y recibe.')
                    except ValueError as exc:st.error(str(exc))
                if st.session_state.get('last_delivery_id'):
                    _delivery_pdf_button(st.session_state['last_delivery_id'],'recent')
    with tabs[4]:
        st.caption('Las anulaciones quedan en la bitácora. Las salidas emitidas se anulan como operación completa.')
        s=db()
        try:
            if has_perm('requests.annul'):
                pool=s.query(MaterialDelivery).filter(MaterialDelivery.status.in_(['Preparada','Emitida'])).order_by(MaterialDelivery.id.desc()).all()
            else:
                pool=[]
            own=s.query(MaterialRequest).filter_by(requested_by=st.session_state['user_id']).filter(
                MaterialRequest.status.in_(['Pendiente','Parcial'])).all()
        finally:s.close()
        if has_perm('requests.annul') and pool:
            choice=st.selectbox('Salida/preparación a anular',
                [f'SR-{x.id:06d} | RQ-{x.request_id:06d} | {x.status}' for x in pool],key='annul_del_choice')
            did=int(choice.split(' | ')[0].split('-')[-1])
            reason=st.text_input('Motivo de anulación de salida')
            if st.button('Anular salida / preparación'):
                try:
                    cancel_delivery(SessionLocal,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
                        dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
                        stock_move_cls=StockMove,user_id=st.session_state['user_id'],dispatch_id=did,reason=reason)
                    audit('material_deliveries',did,'ANNUL',reason.strip());st.success('Salida anulada como unidad; Kardex y requisición recalculados.')
                except ValueError as exc:st.error(str(exc))
        if own or has_perm('requests.annul'):
            s=db()
            try:
                reqs=s.query(MaterialRequest).filter(MaterialRequest.status.in_(['Pendiente','Parcial'])).order_by(MaterialRequest.id.desc()).all()
                if not has_perm('requests.annul'):
                    reqs=[r for r in reqs if r.requested_by==st.session_state['user_id']]
            finally:s.close()
            if reqs:
                choose=st.selectbox('Requisición a cancelar',
                    [f'RQ-{r.id:06d} | {r.status}' for r in reqs],key='annul_req_choice')
                rid=int(choose.split(' | ')[0].split('-')[-1])
                motive=st.text_input('Motivo de cancelación de requisición')
                if st.button('Cancelar requisición'):
                    try:
                        cancel_request(SessionLocal,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
                            dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
                            user_id=st.session_state['user_id'],request_id=rid,reason=motive)
                        audit('material_requests',rid,'CANCEL',motive.strip());st.success('Requisición cancelada.')
                    except ValueError as exc:st.error(str(exc))
    with tabs[5]:
        st.subheader('Comprobante firmado (escaneado)')
        s=db()
        try:
            q=s.query(MaterialDelivery).filter(MaterialDelivery.status.in_(['Emitida','Anulada']))
            rows=q.order_by(MaterialDelivery.id.desc()).limit(500).all()
            if not has_perm('requests.view_all'):
                allowed={r.id for r in s.query(MaterialRequest).filter_by(requested_by=st.session_state['user_id']).all()}
                rows=[x for x in rows if x.request_id in allowed]
        finally:s.close()
        if not rows: st.info('No hay salidas emitidas todavía.')
        else:
            chosen=st.selectbox('Salida',
                [f'SR-{d.id:06d} | {d.status} | RQ-{d.request_id:06d}' for d in rows],key='signed_pdf_choice')
            did=int(chosen.split(' | ')[0].split('-')[-1])
            _delivery_pdf_button(did,'documents')
            if has_perm('requests.issue'):
                upload=st.file_uploader('Adjuntar comprobante firmado y escaneado (PDF)',type=['pdf'],key=f'signed_upload_{did}')
                if st.button('Guardar comprobante firmado',key=f'save_signed_{did}'):
                    if not upload:st.error('Selecciona un archivo PDF.')
                    elif upload.size>12*1024*1024:st.error('El archivo supera el máximo de 12 MB.')
                    else:
                        aid=save_attachment(upload,'material_delivery',did)
                        st.success(f'Documento firmado guardado (adjunto #{aid}).')
            attachments_download_panel('material_delivery','Comprobantes escaneados archivados') if has_perm('requests.view_all') else st.caption('Consulta con bodega para obtener el archivo firmado.')

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
        if not has_perm('assets.create'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); rules=s.query(DepRule).filter_by(active=True).order_by(DepRule.category).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
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
        if not has_perm('assets.edit'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); assets=s.query(Asset).order_by(Asset.id.desc()).all(); rules=s.query(DepRule).filter_by(active=True).order_by(DepRule.category).all(); blocks=s.query(Block).filter_by(active=True).order_by(Block.number,Block.code).all(); s.close()
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
        if not has_perm('assets.delete'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); assets=s.query(Asset).order_by(Asset.id.desc()).all(); sel=st.selectbox('Activo',[f'{a.id} | {a.asset_code} - {a.description} | {a.status}' for a in assets],key='asset_del') if assets else None
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
        if not has_perm('deprules.manage'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); rules=s.query(DepRule).order_by(DepRule.category).all(); s.close(); mode=st.radio('Modo',['Crear nueva','Editar existente'],horizontal=True)
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
        if not has_perm('deprules.manage'):
            st.info('Tu rol no tiene permiso para realizar esta operación.')
        else:
            s=db(); rules=s.query(DepRule).order_by(DepRule.category).all(); sel=st.selectbox('Regla',[f'{r.id} | {r.category}' for r in rules],key='del_rule') if rules else None
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
