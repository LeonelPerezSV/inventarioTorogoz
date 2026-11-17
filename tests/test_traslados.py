"""Pruebas reales del modelo de traslados (sin Streamlit ni red)."""
from pathlib import Path
import sys
import pytest
from sqlalchemy import create_engine, Column, Integer, Float, String, Date, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traslados import create_transfer, annul_transfer, MOVE_IN, MOVE_OUT, _balance

Base=declarative_base()
class Item(Base):
    __tablename__='items'; id=Column(Integer,primary_key=True); active=Column(Boolean,default=True)
class Warehouse(Base):
    __tablename__='warehouses'; id=Column(Integer,primary_key=True);name=Column(String(80));active=Column(Boolean,default=True)
class Block(Base):
    __tablename__='blocks';id=Column(Integer,primary_key=True);active=Column(Boolean,default=True)
class StockMove(Base):
    __tablename__='stock_moves'
    id=Column(Integer,primary_key=True)
    move_date=Column(Date);item_id=Column(Integer,ForeignKey('items.id'))
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'));block_id=Column(Integer,ForeignKey('blocks.id'))
    move_type=Column(String(80));quantity=Column(Float);unit_cost=Column(Float)
    document=Column(String(120));notes=Column(Text);delivered_by=Column(String(160));received_by=Column(String(160));status=Column(String(50),default='Registrado')
    reversal_of=Column(Integer);created_by=Column(Integer);annulled_by=Column(Integer);annulled_at=Column(DateTime)
    annul_reason=Column(Text);updated_by=Column(Integer);updated_at=Column(DateTime)
class WarehouseTransfer(Base):
    __tablename__='warehouse_transfers'
    id=Column(Integer,primary_key=True);move_date=Column(Date);item_id=Column(Integer,ForeignKey('items.id'))
    from_warehouse_id=Column(Integer,ForeignKey('warehouses.id'))
    to_warehouse_id=Column(Integer,ForeignKey('warehouses.id'))
    block_id=Column(Integer,ForeignKey('blocks.id'))
    quantity=Column(Float);unit_cost=Column(Float);document=Column(String(180));notes=Column(Text);delivered_by=Column(String(160));received_by=Column(String(160))
    status=Column(String(40),default='Registrado');out_move_id=Column(Integer,ForeignKey('stock_moves.id'))
    in_move_id=Column(Integer,ForeignKey('stock_moves.id'));created_by=Column(Integer)
    annulled_by=Column(Integer);annulled_at=Column(DateTime);annul_reason=Column(Text)

@pytest.fixture()
def factory(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "prueba.db"}')
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine, expire_on_commit=False)
    s=factory()
    s.add(Item(id=1,active=True))
    s.add_all([Warehouse(id=i,name=f'Bodega {i}',active=True) for i in range(1,5)])
    s.add_all([Block(id=1,active=True),Block(id=2,active=True)])
    s.add(StockMove(item_id=1,warehouse_id=1,block_id=1,move_type='Entrada',quantity=100,unit_cost=5,status='Registrado'))
    s.commit();s.close()
    try:
        yield factory
    finally:
        engine.dispose()

def make(factory, **overrides):
    options={'item_id':1,'from_warehouse_id':1,'to_warehouse_id':2,'block_id':1,'quantity':30,'user_id':99,'document':'Prueba 1'}
    options.update(overrides)
    return create_transfer(factory,transfer_cls=WarehouseTransfer,stock_move_cls=StockMove,
                           item_cls=Item,warehouse_cls=Warehouse,block_cls=Block,**options)

def cancel(factory,tid,reason='Error de prueba'):
    return annul_transfer(factory,transfer_cls=WarehouseTransfer,stock_move_cls=StockMove,
                          item_cls=Item,transfer_id=tid,reason=reason,user_id=99)

def stock(factory,wh,block=1):
    s=factory()
    try: return _balance(s,StockMove,1,wh,block)
    finally:s.close()

def test_atomic_transfer_changes_both_warehouses(factory):
    tid,reference=make(factory)
    assert reference=='TR-000001'
    assert stock(factory,1)==70
    assert stock(factory,2)==30
    assert stock(factory,3)==0
    s=factory();t=s.get(WarehouseTransfer,tid)
    assert s.get(StockMove,t.out_move_id).move_type==MOVE_OUT
    assert s.get(StockMove,t.in_move_id).move_type==MOVE_IN
    assert s.get(StockMove,t.in_move_id).unit_cost==5
    s.close()

def test_reject_insufficient_stock_without_partial_moves(factory):
    with pytest.raises(ValueError, match='Existencia insuficiente'):
        make(factory,quantity=120)
    assert stock(factory,1)==100
    assert stock(factory,2)==0
    s=factory();assert s.query(WarehouseTransfer).count()==0;assert s.query(StockMove).count()==1;s.close()

def test_reject_same_origin_and_destination(factory):
    with pytest.raises(ValueError,match='diferentes'):
        make(factory,to_warehouse_id=1)
    assert stock(factory,1)==100

def test_four_warehouse_chain(factory):
    make(factory,quantity=40)
    make(factory,from_warehouse_id=2,to_warehouse_id=3,quantity=15)
    make(factory,from_warehouse_id=3,to_warehouse_id=4,quantity=8)
    assert [stock(factory,i) for i in range(1,5)]==[60,25,7,8]

def test_annul_reverts_both_without_double_subtract(factory):
    tid,_=make(factory)
    cancel(factory,tid)
    assert stock(factory,1)==100
    assert stock(factory,2)==0
    s=factory(); t=s.get(WarehouseTransfer,tid)
    assert t.status=='Anulado'
    assert s.get(StockMove,t.out_move_id).status=='Anulado'
    assert s.get(StockMove,t.in_move_id).status=='Anulado'
    s.close()
    with pytest.raises(ValueError,match='ya está anulado'):
        cancel(factory,tid)

def test_cannot_annul_after_destination_consumption(factory):
    tid,_=make(factory)
    s=factory()
    s.add(StockMove(item_id=1,warehouse_id=2,block_id=1,move_type='Salida',quantity=24,unit_cost=5,status='Registrado'))
    s.commit();s.close()
    with pytest.raises(ValueError,match='No se puede anular'):
        cancel(factory,tid)
    assert stock(factory,1)==70
    assert stock(factory,2)==6

def test_transfers_are_block_specific(factory):
    with pytest.raises(ValueError,match='insuficiente'):
        make(factory,block_id=2,quantity=1)
    assert stock(factory,1,2)==0
    assert stock(factory,1,1)==100


def test_reject_invalid_block(factory):
    with pytest.raises(ValueError, match='bloque'):
        make(factory,block_id=None)
