import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from requisiciones import create_request, prepare_delivery, issue_delivery, cancel_delivery, cancel_request, remaining_lines
from traslados import _balance
from comprobantes_requisicion import pdf_requisicion, pdf_salida

Base=declarative_base()
class Item(Base):
    __tablename__='items';id=Column(Integer,primary_key=True);sku=Column(String);description=Column(String);unit=Column(String,default='Unidad');active=Column(Integer,default=1)
class Warehouse(Base):
    __tablename__='warehouses';id=Column(Integer,primary_key=True);name=Column(String);active=Column(Integer,default=1)
class Block(Base):
    __tablename__='blocks';id=Column(Integer,primary_key=True);number=Column(Integer);code=Column(String);active=Column(Integer,default=1)
class StockMove(Base):
    __tablename__='stock_moves'
    id=Column(Integer,primary_key=True);move_date=Column(Date);item_id=Column(Integer,ForeignKey('items.id'))
    warehouse_id=Column(Integer,ForeignKey('warehouses.id'));block_id=Column(Integer,ForeignKey('blocks.id'))
    move_type=Column(String);quantity=Column(Float);unit_cost=Column(Float);document=Column(String)
    notes=Column(String);status=Column(String,default='Registrado');reversal_of=Column(Integer)
    created_by=Column(Integer);delivered_by=Column(String);received_by=Column(String)
    consumption_type=Column(String);consumption_detail=Column(String);consumption_lot=Column(String)
    consumption_sector=Column(String);consumption_subsector=Column(String)
    annulled_at=Column(DateTime);annulled_by=Column(Integer);annul_reason=Column(String);updated_at=Column(DateTime);updated_by=Column(Integer)
class MaterialRequest(Base):
    __tablename__='material_requests'
    id=Column(Integer,primary_key=True);request_date=Column(Date)
    requested_by=Column(Integer);requested_for=Column(String)
    warehouse_id=Column(Integer);block_id=Column(Integer)
    consumption_type=Column(String);consumption_detail=Column(String);consumption_lot=Column(String)
    consumption_sector=Column(String);consumption_subsector=Column(String)
    notes=Column(String);status=Column(String,default='Pendiente')
    cancelled_by=Column(Integer);cancelled_at=Column(DateTime);cancel_reason=Column(String)
class MaterialRequestLine(Base):
    __tablename__='material_request_lines'
    id=Column(Integer,primary_key=True);request_id=Column(Integer,ForeignKey('material_requests.id'))
    item_id=Column(Integer);quantity=Column(Float)
class MaterialDelivery(Base):
    __tablename__='material_deliveries'
    id=Column(Integer,primary_key=True);request_id=Column(Integer,ForeignKey('material_requests.id'))
    dispatch_date=Column(Date);status=Column(String,default='Preparada')
    prepared_by=Column(Integer);delivered_by=Column(String);received_by=Column(String)
    notes=Column(String);issued_by=Column(Integer);issued_at=Column(DateTime)
    cancelled_by=Column(Integer);cancelled_at=Column(DateTime);cancel_reason=Column(String)
class MaterialDeliveryLine(Base):
    __tablename__='material_delivery_lines'
    id=Column(Integer,primary_key=True);dispatch_id=Column(Integer,ForeignKey('material_deliveries.id'))
    request_line_id=Column(Integer,ForeignKey('material_request_lines.id'))
    quantity=Column(Float);move_id=Column(Integer,ForeignKey('stock_moves.id'))

class TestRequisiciones(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'test.db'),future=True)
        Base.metadata.create_all(self.engine)
        self.F=sessionmaker(bind=self.engine,expire_on_commit=False,autoflush=False)
        s=self.F()
        s.add_all([Item(id=1,sku='TUB',description='Tubería PVC'),Item(id=2,sku='VAL',description='Válvula'),
                   Warehouse(id=1,name='Central'), Block(id=1,number=1,code='LOC-ACOM')])
        s.add_all([
            StockMove(item_id=1,warehouse_id=1,block_id=1,move_type='Entrada',quantity=100,unit_cost=5,status='Registrado'),
            StockMove(item_id=2,warehouse_id=1,block_id=1,move_type='Entrada',quantity=30,unit_cost=10,status='Registrado'),
        ]);s.commit();s.close()
    def tearDown(self):
        # En Windows, SQLite mantiene test.db bloqueado hasta cerrar el engine.
        self.engine.dispose()
        self.tmp.cleanup()
    def create(self,quantities=None):
        return create_request(self.F,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
            item_cls=Item,warehouse_cls=Warehouse,block_cls=Block,user_id=25,
            warehouse_id=1,block_id=1,lines=quantities or {1:50,2:10},
            requested_for='Cuadrilla Alfa',classification={'consumption_type':'Redes','consumption_detail':'Prueba'})
    def prepare(self,rid,quantities):
        return prepare_delivery(self.F,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
            dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
            item_cls=Item,stock_move_cls=StockMove,user_id=8,request_id=rid,
            quantities=quantities,delivered_by='Almacén',received_by='Campo')
    def issue(self,did):
        return issue_delivery(self.F,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
            dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
            item_cls=Item,stock_move_cls=StockMove,user_id=8,dispatch_id=did)
    def test_request_does_not_debit(self):
        self.create()
        s=self.F();self.assertEqual(_balance(s,StockMove,1,1,1),100);s.close()
    def test_preparation_does_not_debit(self):
        rid=self.create();self.prepare(rid,{1:20,2:4})
        s=self.F();self.assertEqual(_balance(s,StockMove,1,1,1),100);s.close()
    def test_issue_creates_two_stock_moves(self):
        rid=self.create();did=self.prepare(rid,{1:50,2:10});self.issue(did)
        s=self.F()
        self.assertEqual(s.get(MaterialRequest,rid).status,'Atendida')
        self.assertEqual(_balance(s,StockMove,1,1,1),50)
        self.assertEqual(_balance(s,StockMove,2,1,1),20)
        self.assertEqual(s.query(MaterialDeliveryLine).filter_by(dispatch_id=did).count(),2)
        self.assertEqual(s.get(MaterialDelivery,did).status,'Emitida');s.close()
    def test_partial_then_complete(self):
        rid=self.create();s=self.F();ids=[x.id for x in s.query(MaterialRequestLine).filter_by(request_id=rid).order_by(MaterialRequestLine.id).all()];s.close()
        d1=self.prepare(rid,{ids[0]:20,ids[1]:4});self.issue(d1)
        s=self.F();self.assertEqual(s.get(MaterialRequest,rid).status,'Parcial');s.close()
        d2=self.prepare(rid,{ids[0]:30,ids[1]:6});self.issue(d2)
        s=self.F();self.assertEqual(s.get(MaterialRequest,rid).status,'Atendida');self.assertEqual(_balance(s,StockMove,1,1,1),50);s.close()
    def test_exceed_pending_rolls_back(self):
        rid=self.create({1:5})
        with self.assertRaises(ValueError):self.prepare(rid,{1:6})
        s=self.F();self.assertEqual(s.query(MaterialDelivery).count(),0);s.close()
    def test_exceed_stock_rolls_back(self):
        rid=self.create({1:200})
        with self.assertRaises(ValueError):self.prepare(rid,{1:120})
        s=self.F();self.assertEqual(s.query(MaterialDelivery).count(),0);s.close()
    def test_cannot_prepare_more_than_remaining_with_another_preparation(self):
        rid=self.create({1:10})
        self.prepare(rid,{1:7})
        with self.assertRaises(ValueError):
            self.prepare(rid,{1:5})
        s=self.F()
        self.assertEqual(s.query(MaterialDelivery).count(),1)
        self.assertEqual(_balance(s,StockMove,1,1,1),100)
        s.close()

    def test_issue_refuses_after_stock_changes(self):
        rid=self.create();did=self.prepare(rid,{1:50})
        s=self.F();s.add(StockMove(item_id=1,warehouse_id=1,block_id=1,move_type='Salida',quantity=70,status='Registrado'));s.commit();s.close()
        with self.assertRaises(ValueError):self.issue(did)
        s=self.F();self.assertEqual(s.get(MaterialDelivery,did).status,'Preparada');self.assertEqual(_balance(s,StockMove,1,1,1),30);s.close()
    def test_cancel_reverses_all_lines(self):
        rid=self.create();did=self.prepare(rid,{1:50,2:10});self.issue(did)
        cancel_delivery(self.F,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
            dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
            stock_move_cls=StockMove,user_id=6,dispatch_id=did,reason='Error pedido')
        s=self.F();self.assertEqual(_balance(s,StockMove,1,1,1),100)
        self.assertEqual(s.get(MaterialRequest,rid).status,'Pendiente');self.assertEqual(s.get(MaterialDelivery,did).status,'Anulada');s.close()
    def test_request_cancel_rejects_issued(self):
        rid=self.create();did=self.prepare(rid,{1:10});self.issue(did)
        with self.assertRaises(ValueError):
            cancel_request(self.F,request_cls=MaterialRequest,line_cls=MaterialRequestLine,
                dispatch_cls=MaterialDelivery,dispatch_line_cls=MaterialDeliveryLine,
                user_id=25,request_id=rid,reason='Cancelación')
    def test_pdf_signatures_and_folios(self):
        common={'requisicion':'RQ-000001','salida':'SR-000007','fecha':date(2026,11,16),
            'estado':'Emitida','bodega':'Bodega central','bloque':'1 - INSTALACION','solicitante':'Juan',
            'cuadrilla':'Cuadrilla Alfa','entrega':'Maria','recibe':'Roberto','registra':'Luis',
            'lineas':[{'sku':'TUB001','producto':'Tubería PVC','unidad':'unidad','solicitado':10,'entregado':8}]}
        out=pdf_salida(common)
        self.assertTrue(out.startswith(b'%PDF-'))
        self.assertTrue(len(out)>1900)
        self.assertTrue(pdf_requisicion({**common,'salida':None}).startswith(b'%PDF-'))

if __name__=='__main__':unittest.main()
