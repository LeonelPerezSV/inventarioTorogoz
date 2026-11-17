"""Requisiciones de campo y entrega de almacén.

Todas las mutaciones de inventario emitidas por el módulo se confirman en
una sola transacción. Las solicitudes y preparaciones NO modifican el Kardex.
"""
from datetime import date, datetime
from collections import defaultdict
from sqlalchemy import func
from traslados import _balance, _cost_reference, _lock_item

EPS = 1e-8


def _numeric_lines(lines):
    result = {}
    for item_id, amount in lines.items():
        key = int(item_id)
        qty = float(amount)
        if qty <= 0:
            raise ValueError('Todas las cantidades deben ser mayores que cero.')
        if key in result:
            raise ValueError('No se puede repetir un producto en la misma requisición.')
        result[key] = qty
    if not result:
        raise ValueError('Agrega al menos un producto.')
    return result


def _req_status(session, req, line_cls, dispatch_cls, dispatch_line_cls):
    ordered = session.query(line_cls).filter_by(request_id=req.id).all()
    emitted = {ln.id: 0.0 for ln in ordered}
    rows = session.query(dispatch_line_cls).join(
        dispatch_cls, dispatch_line_cls.dispatch_id == dispatch_cls.id
    ).filter(dispatch_cls.request_id == req.id, dispatch_cls.status == 'Emitida').all()
    for row in rows:
        if row.request_line_id in emitted:
            emitted[row.request_line_id] += float(row.quantity)
    if not ordered:
        req.status = 'Pendiente'
    elif all(emitted[x.id] >= float(x.quantity) - EPS for x in ordered):
        req.status = 'Atendida'
    elif any(v > EPS for v in emitted.values()):
        req.status = 'Parcial'
    else:
        req.status = 'Pendiente'
    return emitted


def remaining_lines(session, req_id, line_cls, dispatch_cls, dispatch_line_cls):
    lines = session.query(line_cls).filter_by(request_id=req_id).order_by(line_cls.id).all()
    emitted = defaultdict(float)
    rows = session.query(dispatch_line_cls).join(
        dispatch_cls, dispatch_line_cls.dispatch_id == dispatch_cls.id
    ).filter(dispatch_cls.request_id == req_id, dispatch_cls.status == 'Emitida').all()
    for row in rows:
        emitted[row.request_line_id] += float(row.quantity)
    return [(line, max(0.0, float(line.quantity) - emitted[line.id])) for line in lines]


def create_request(session_factory, *, request_cls, line_cls, item_cls, warehouse_cls,
                   block_cls, user_id, warehouse_id, block_id, lines,
                   requested_for='', notes='', date_requested=None,
                   classification=None):
    data = _numeric_lines(lines)
    s = session_factory()
    try:
        with s.begin():
            w = s.get(warehouse_cls, warehouse_id)
            b = s.get(block_cls, block_id)
            if not w or not w.active or not b or not b.active:
                raise ValueError('Selecciona una bodega y un bloque activos.')
            for item_id in data:
                item=s.get(item_cls,item_id)
                if not item or not item.active:
                    raise ValueError('Producto inexistente o inactivo.')
            fields=classification or {}
            req=request_cls(
                request_date=date_requested or date.today(),
                requested_by=user_id,
                requested_for=(requested_for or '').strip(),
                warehouse_id=warehouse_id,block_id=block_id,
                consumption_type=fields.get('consumption_type'),
                consumption_detail=fields.get('consumption_detail'),
                consumption_lot=fields.get('consumption_lot'),
                consumption_sector=fields.get('consumption_sector'),
                consumption_subsector=fields.get('consumption_subsector'),
                notes=(notes or '').strip(),status='Pendiente'
            )
            s.add(req);s.flush()
            for item_id,qty in data.items():
                s.add(line_cls(request_id=req.id,item_id=item_id,quantity=qty))
            request_id=req.id
        return request_id
    finally:
        s.close()


def prepare_delivery(session_factory, *, request_cls, line_cls, dispatch_cls,
                     dispatch_line_cls, item_cls, stock_move_cls, user_id,
                     request_id, quantities, delivered_by='', received_by='',
                     notes=''):
    quantities=_numeric_lines(quantities)
    if not str(delivered_by or '').strip() or not str(received_by or '').strip():
        raise ValueError('Debes indicar quién entrega y quién recibe.')
    s=session_factory()
    try:
        with s.begin():
            req=s.query(request_cls).filter_by(id=request_id).with_for_update().one_or_none()
            if not req or req.status in ('Cancelada','Atendida'):
                raise ValueError('La requisición no está pendiente de atención.')
            remaining=dict((ln.id, available) for ln, available in remaining_lines(
                s,request_id,line_cls,dispatch_cls,dispatch_line_cls))
            req_lines={x.id:x for x in s.query(line_cls).filter_by(request_id=request_id).all()}
            # Evita preparar dos veces el mismo saldo pendiente mientras hay
            # preparaciones activas de esta requisición.
            pending_prepared=defaultdict(float)
            prepared_rows=s.query(dispatch_line_cls).join(
                dispatch_cls, dispatch_line_cls.dispatch_id==dispatch_cls.id
            ).filter(dispatch_cls.request_id==request_id,dispatch_cls.status=='Preparada').all()
            for row in prepared_rows:
                pending_prepared[row.request_line_id]+=float(row.quantity)
            for rid,qty in quantities.items():
                if rid not in req_lines or qty > remaining.get(rid,0)-pending_prepared[rid]+EPS:
                    raise ValueError('La cantidad supera lo pendiente disponible para preparar.')
            # Validación preliminar de stock; se repite bajo bloqueo al emitir.
            for rid,qty in quantities.items():
                line=req_lines[rid]
                stock=_balance(s,stock_move_cls,line.item_id,req.warehouse_id,req.block_id)
                if qty > stock+EPS:
                    raise ValueError(f'Existencia insuficiente para {line.item_id}. Disponible: {stock:g}.')
            disp=dispatch_cls(
                request_id=req.id,dispatch_date=date.today(),status='Preparada',
                prepared_by=user_id,delivered_by=(delivered_by or '').strip(),
                received_by=(received_by or '').strip(),notes=(notes or '').strip()
            )
            s.add(disp);s.flush()
            for rid,qty in quantities.items():
                s.add(dispatch_line_cls(dispatch_id=disp.id,request_line_id=rid,quantity=qty))
            dispatch_id=disp.id
        return dispatch_id
    finally:
        s.close()


def issue_delivery(session_factory, *, request_cls, line_cls, dispatch_cls,
                   dispatch_line_cls, item_cls, stock_move_cls, user_id, dispatch_id,
                   classification=None):
    s=session_factory()
    try:
        with s.begin():
            disp=s.query(dispatch_cls).filter_by(id=dispatch_id).with_for_update().one_or_none()
            if not disp or disp.status!='Preparada':
                raise ValueError('Esta preparación ya fue emitida o está cancelada.')
            req=s.query(request_cls).filter_by(id=disp.request_id).with_for_update().one_or_none()
            if not req or req.status=='Cancelada':
                raise ValueError('La requisición fue cancelada.')
            entries=s.query(dispatch_line_cls).filter_by(dispatch_id=disp.id).all()
            if not entries:
                raise ValueError('La preparación está vacía.')
            remainder=dict((ln.id, qty) for ln,qty in remaining_lines(
                s,req.id,line_cls,dispatch_cls,dispatch_line_cls))
            req_lines={ln.id:ln for ln in s.query(line_cls).filter_by(request_id=req.id).all()}
            product_ids=sorted({req_lines[entry.request_line_id].item_id for entry in entries})
            for product_id in product_ids:
                _lock_item(s,item_cls,product_id)
            for entry in entries:
                line=req_lines[entry.request_line_id]
                if entry.quantity>remainder.get(line.id,0)+EPS:
                    raise ValueError('El pedido pendiente cambió; la preparación debe revisarse.')
                stock=_balance(s,stock_move_cls,line.item_id,req.warehouse_id,req.block_id)
                if entry.quantity>stock+EPS:
                    raise ValueError(f'Stock insuficiente para {line.item_id}; disponible {stock:g}.')
            classification={k:getattr(req,k,None) for k in (
                'consumption_type','consumption_detail','consumption_lot',
                'consumption_sector','consumption_subsector')}
            for entry in entries:
                line=req_lines[entry.request_line_id]
                cost=_cost_reference(s,stock_move_cls,line.item_id,req.warehouse_id,req.block_id)
                move=stock_move_cls(
                    move_date=date.today(),item_id=line.item_id,
                    warehouse_id=req.warehouse_id,block_id=req.block_id,
                    move_type='Salida',quantity=float(entry.quantity),unit_cost=cost,
                    document=f'SR-{disp.id:06d}',
                    notes=f'Requisición RQ-{req.id:06d}; {(disp.notes or "").strip()}',
                    status='Registrado',created_by=user_id,
                    delivered_by=disp.delivered_by,received_by=disp.received_by,
                    **classification
                )
                s.add(move);s.flush();entry.move_id=move.id
            disp.status='Emitida'
            disp.issued_at=datetime.now()
            disp.issued_by=user_id
            s.flush()
            _req_status(s,req,line_cls,dispatch_cls,dispatch_line_cls)
        return dispatch_id
    finally:
        s.close()


def cancel_delivery(session_factory, *, request_cls,line_cls,dispatch_cls,
                    dispatch_line_cls,stock_move_cls,user_id,dispatch_id,reason):
    if not (reason or '').strip():
        raise ValueError('Es obligatorio indicar el motivo.')
    s=session_factory()
    try:
        with s.begin():
            disp=s.query(dispatch_cls).filter_by(id=dispatch_id).with_for_update().one_or_none()
            if not disp or disp.status not in ('Preparada','Emitida'):
                raise ValueError('La salida ya no puede cancelarse.')
            req=s.query(request_cls).filter_by(id=disp.request_id).with_for_update().one_or_none()
            # Anular salidas libera unidades. Como están agrupadas, se anulan todas juntas.
            if disp.status=='Emitida':
                for ln in s.query(dispatch_line_cls).filter_by(dispatch_id=disp.id).all():
                    m=s.get(stock_move_cls,ln.move_id)
                    if not m or m.status!='Registrado':
                        raise ValueError('La salida tiene un movimiento inconsistente. Requiere revisión.')
                    m.status='Anulado';m.annulled_at=datetime.now();m.annulled_by=user_id
                    m.annul_reason=reason.strip();m.updated_at=datetime.now();m.updated_by=user_id
            disp.status='Anulada';disp.cancelled_at=datetime.now();disp.cancelled_by=user_id
            disp.cancel_reason=reason.strip()
            s.flush()
            _req_status(s,req,line_cls,dispatch_cls,dispatch_line_cls)
        return True
    finally:
        s.close()


def cancel_request(session_factory, *, request_cls,line_cls,dispatch_cls,
                   dispatch_line_cls,user_id,request_id,reason):
    if not str(reason).strip():
        raise ValueError('Debes indicar un motivo de cancelación.')
    s=session_factory()
    try:
        with s.begin():
            req=s.query(request_cls).filter_by(id=request_id).with_for_update().one_or_none()
            if not req or req.status in ('Cancelada','Atendida'):
                raise ValueError('La requisición no puede cancelarse en ese estado.')
            # Evitar cancelación de requisiciones con entregas emitidas.
            dispatched=s.query(dispatch_cls).filter_by(request_id=req.id,status='Emitida').count()
            if dispatched:
                raise ValueError('La requisición tiene salidas emitidas. Anula primero las salidas.')
            for prep in s.query(dispatch_cls).filter_by(request_id=req.id,status='Preparada').all():
                prep.status='Anulada';prep.cancelled_by=user_id
                prep.cancelled_at=datetime.now();prep.cancel_reason='Cancelada junto con la requisición'
            req.status='Cancelada';req.cancelled_by=user_id
            req.cancelled_at=datetime.now();req.cancel_reason=reason.strip()
        return True
    finally:
        s.close()
