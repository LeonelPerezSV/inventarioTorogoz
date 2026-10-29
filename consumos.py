"""Catálogo de clasificación de salidas/consumos del proyecto (Hoja2 del maestro)."""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / 'data' / 'distribucion_consumos.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
CAMPOS = ('consumption_type', 'consumption_detail', 'consumption_lot', 'consumption_sector', 'consumption_subsector')


def is_outbound(move_type):
    """Ambas clases de egreso restan existencias y requieren clasificación."""
    return move_type in ('Salida', 'Devolución salida')


def empty_classification():
    return {key: None for key in CAMPOS}


def validate_classification(move_type, values):
    """Devuelve datos limpios o lanza ValueError. No modifica inventarios."""
    if not is_outbound(move_type):
        return empty_classification()
    values = values or {}
    kind = values.get('consumption_type')
    if kind not in CONFIG['tipos']:
        raise ValueError('Selecciona un tipo de consumo válido.')
    rule = CONFIG['tipos'][kind]
    subtype = values.get('consumption_detail')
    lot = values.get('consumption_lot')
    sector = values.get('consumption_sector')
    subsector = values.get('consumption_subsector')
    if rule['opciones_detalle']:
        if subtype not in rule['opciones_detalle']:
            raise ValueError(f"Selecciona un {rule['etiqueta_detalle'].lower()} válido.")
    else:
        subtype = None
    if rule['requiere_geografia']:
        if lot not in CONFIG['lotes']:
            raise ValueError('Selecciona un lote válido.')
        if sector not in CONFIG['sectores']:
            raise ValueError('Selecciona un sector válido.')
        if subsector not in CONFIG['subsectores_por_sector'][sector]:
            raise ValueError('El subsector debe corresponder al sector seleccionado.')
    else:
        lot = sector = subsector = None
    return dict(zip(CAMPOS, [kind, subtype, lot, sector, subsector]))


def describe_classification(values):
    values = values or {}
    return ' / '.join(str(values[k]) for k in CAMPOS if values.get(k))


def render_classification(st, prefix, move_type, existing=None):
    """Muestra controles fuera de st.form para actualizar cascadas en cada cambio.

    Importante: el widget 'Tipo de movimiento' también debe estar fuera del formulario.
    """
    if not is_outbound(move_type):
        return empty_classification()
    existing = existing or {}
    st.markdown('#### Destino del consumo')
    tipos = list(CONFIG['tipos'])
    default_type = existing.get('consumption_type')
    type_index = tipos.index(default_type) if default_type in tipos else None
    kind = st.selectbox(
        'Tipo de consumo *', tipos, index=type_index,
        placeholder='Selecciona el destino del consumo', key=f'{prefix}_consumption_type'
    )
    result = empty_classification()
    result['consumption_type'] = kind
    if not kind:
        st.info('Selecciona el tipo de consumo para habilitar los campos correspondientes.')
        return result
    rule = CONFIG['tipos'][kind]
    if rule['opciones_detalle']:
        choices = rule['opciones_detalle']
        old = existing.get('consumption_detail') if default_type == kind else None
        ix = choices.index(old) if old in choices else None
        result['consumption_detail'] = st.selectbox(
            f"{rule['etiqueta_detalle']} *", choices, index=ix,
            placeholder=f"Selecciona {rule['etiqueta_detalle'].lower()}",
            key=f'{prefix}_detail_{kind}'
        )
    if rule['requiere_geografia']:
        c1, c2, c3 = st.columns(3)
        old_lot = existing.get('consumption_lot') if default_type == kind else None
        old_sector = existing.get('consumption_sector') if default_type == kind else None
        li = CONFIG['lotes'].index(old_lot) if old_lot in CONFIG['lotes'] else None
        si = CONFIG['sectores'].index(old_sector) if old_sector in CONFIG['sectores'] else None
        result['consumption_lot'] = c1.selectbox(
            'Lote *', CONFIG['lotes'], index=li, placeholder='Selecciona lote', key=f'{prefix}_lot_{kind}'
        )
        sector = c2.selectbox(
            'Sector *', CONFIG['sectores'], index=si, placeholder='Selecciona sector', key=f'{prefix}_sector_{kind}'
        )
        result['consumption_sector'] = sector
        if sector:
            subs = CONFIG['subsectores_por_sector'][sector]
            old_sub = existing.get('consumption_subsector') if old_sector == sector and default_type == kind else None
            ix = subs.index(old_sub) if old_sub in subs else None
            result['consumption_subsector'] = c3.selectbox(
                'Subsector *', subs, index=ix, placeholder='Selecciona subsector',
                key=f'{prefix}_subsector_{kind}_{sector}'
            )
        else:
            c3.selectbox('Subsector *', [], index=None, placeholder='Primero selecciona sector', disabled=True)
    return result
