"""Lógica de traslados interbodega.

Dos movimientos de Kardex por traslado dentro de una sola transacción.
No necesita redes ni equipos externos para las pruebas locales.
"""
from datetime import date, datetime
from sqlalchemy import text

MOVE_OUT = 'Traslado salida'
MOVE_IN = 'Traslado entrada'


def _effect(m):
    if m.move_type in ('Entrada', 'Devolución entrada', MOVE_IN):
        return float(m.quantity)
    if m.move_type in ('Salida', 'Devolución salida', MOVE_OUT):
        return -float(m.quantity)
    return 0.0


def _balance(session, stock_move_cls, item_id, warehouse_id, block_id):
    q = session.query(stock_move_cls).filter(
        stock_move_cls.item_id == item_id,
        stock_move_cls.warehouse_id == warehouse_id,
        stock_move_cls.status == 'Registrado',
        stock_move_cls.reversal_of.is_(None)
    )
    q = q.filter(stock_move_cls.block_id == block_id) if block_id is not None else q.filter(stock_move_cls.block_id.is_(None))
    return sum(_effect(m) for m in q.all())


def _cost_reference(session, stock_move_cls, item_id, warehouse_id, block_id):
    q = session.query(stock_move_cls).filter(
        stock_move_cls.item_id == item_id,
        stock_move_cls.warehouse_id == warehouse_id,
        stock_move_cls.status == 'Registrado',
        stock_move_cls.reversal_of.is_(None),
        stock_move_cls.move_type.in_(['Entrada', 'Devolución entrada', MOVE_IN])
    )
    q = q.filter(stock_move_cls.block_id == block_id) if block_id is not None else q.filter(stock_move_cls.block_id.is_(None))
    rows = q.all()
    qty = sum(float(m.quantity) for m in rows)
    return sum(float(m.quantity) * float(m.unit_cost or 0) for m in rows) / qty if qty else 0.0


def _lock_item(session, item_cls, item_id):
    # En PostgreSQL, bloqueamos la fila del producto para serializar traslados
    # simultáneos de ese producto. SQLite serializa las escrituras de su lado.
    item = session.query(item_cls).filter(item_cls.id == item_id).with_for_update().one_or_none()
    if item is None or not item.active:
        raise ValueError('El producto no existe o está inactivo.')
    return item


def create_transfer(session_factory, *, transfer_cls, stock_move_cls, item_cls, warehouse_cls,
                    block_cls, item_id, from_warehouse_id, to_warehouse_id, block_id,
                    quantity, move_date=None, document='', notes='', user_id=None,
                    delivered_by='', received_by=''):
    qty = float(quantity)
    if qty <= 0:
        raise ValueError('La cantidad debe ser mayor que cero.')
    if from_warehouse_id == to_warehouse_id:
        raise ValueError('La bodega de origen y destino deben ser diferentes.')
    if block_id is None:
        raise ValueError('Selecciona el bloque que corresponde al traslado.')
    s=session_factory()
    try:
        with s.begin():
            _lock_item(s, item_cls, item_id)
            origin=s.get(warehouse_cls, from_warehouse_id)
            destination=s.get(warehouse_cls, to_warehouse_id)
            if not origin or not origin.active or not destination or not destination.active:
                raise ValueError('Ambas bodegas deben existir y estar activas.')
            block=s.get(block_cls,block_id)
            if not block or not block.active:
                raise ValueError('El bloque seleccionado no está activo.')
            available=_balance(s,stock_move_cls,item_id,from_warehouse_id,block_id)
            if qty > available + 1e-8:
                raise ValueError(f'Existencia insuficiente en origen y bloque. Disponible: {available:g}.')
            cost=_cost_reference(s,stock_move_cls,item_id,from_warehouse_id,block_id)
            when=move_date or date.today()
            t=transfer_cls(move_date=when,item_id=item_id,
                           from_warehouse_id=from_warehouse_id,to_warehouse_id=to_warehouse_id,
                           block_id=block_id,quantity=qty,unit_cost=cost,document=document,
                           notes=notes,status='Registrado',created_by=user_id,
                           delivered_by=delivered_by,received_by=received_by)
            s.add(t)
            s.flush()
            reference=f'TR-{t.id:06d}'
            outbound=stock_move_cls(move_date=when,item_id=item_id,warehouse_id=from_warehouse_id,
                         block_id=block_id,move_type=MOVE_OUT,quantity=qty,unit_cost=cost,
                         document=reference,notes=f'Traslado {reference} a bodega {destination.name}; {notes or ""}',
                         status='Registrado',created_by=user_id,
                         delivered_by=delivered_by,received_by=received_by)
            inbound=stock_move_cls(move_date=when,item_id=item_id,warehouse_id=to_warehouse_id,
                         block_id=block_id,move_type=MOVE_IN,quantity=qty,unit_cost=cost,
                         document=reference,notes=f'Traslado {reference} desde bodega {origin.name}; {notes or ""}',
                         status='Registrado',created_by=user_id,
                         delivered_by=delivered_by,received_by=received_by)
            s.add_all([outbound,inbound])
            s.flush()
            t.out_move_id=outbound.id
            t.in_move_id=inbound.id
            transfer_id=t.id
        return transfer_id,reference
    finally:
        s.close()


def annul_transfer(session_factory, *, transfer_cls, stock_move_cls, item_cls,
                   transfer_id, reason, user_id=None):
    if not str(reason).strip():
        raise ValueError('Debes registrar el motivo de anulación.')
    s=session_factory()
    try:
        with s.begin():
            t=s.query(transfer_cls).filter(transfer_cls.id == transfer_id).with_for_update().one_or_none()
            if t is None:
                raise ValueError('El traslado no existe.')
            if t.status != 'Registrado':
                raise ValueError('Este traslado ya está anulado.')
            _lock_item(s,item_cls,t.item_id)
            # Anular la entrada de destino solo si los movimientos posteriores
            # no dejan existencia negativa en el destino.
            available=_balance(s,stock_move_cls,t.item_id,t.to_warehouse_id,t.block_id)
            if available + 1e-8 < float(t.quantity):
                raise ValueError(f'No se puede anular: destino tiene {available:g} unidades disponibles, y el traslado fue por {t.quantity:g}.')
            out=s.get(stock_move_cls,t.out_move_id)
            inc=s.get(stock_move_cls,t.in_move_id)
            if not out or not inc or out.status!='Registrado' or inc.status!='Registrado':
                raise ValueError('El Kardex del traslado está inconsistente. Requiere revisión.')
            out.status='Anulado'
            inc.status='Anulado'
            when=datetime.now()
            for m in (out,inc):
                m.annulled_by=user_id
                m.annulled_at=when
                m.annul_reason=reason.strip()
                m.updated_by=user_id
                m.updated_at=when
            t.status='Anulado'
            t.annulled_by=user_id
            t.annulled_at=when
            t.annul_reason=reason.strip()
        return True
    finally:
        s.close()
