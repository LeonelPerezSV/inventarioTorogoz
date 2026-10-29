import unittest
from consumos import CONFIG, CAMPOS, validate_classification, empty_classification

class ConsumosTest(unittest.TestCase):
    def test_seis_tipos(self):
        self.assertEqual(len(CONFIG['tipos']), 6)

    def test_entrada_sin_clasificacion(self):
        self.assertEqual(validate_classification('Entrada', {}), empty_classification())

    def test_acometida(self):
        value = {'consumption_type':'Acometida', 'consumption_detail':'Tipo C',
                 'consumption_lot':'1','consumption_sector':'1','consumption_subsector':'1.10'}
        self.assertEqual(validate_classification('Salida', value)['consumption_subsector'],'1.10')

    def test_sector_no_corresponde(self):
        with self.assertRaises(ValueError):
            validate_classification('Salida', {
                'consumption_type':'Reparacion de Fuga','consumption_lot':'1',
                'consumption_sector':'1','consumption_subsector':'3.02'})

    def test_cruce_aereo_no_exige_mas(self):
        val=validate_classification('Salida', {'consumption_type':'Cruce Aereo'})
        self.assertTrue(all(val[key] is None for key in CAMPOS if key!='consumption_type'))

    def test_subtipos_redes_y_tanque(self):
        for kind, subtype in [('Redes','Calle Mariona'),('Tanque','Corinto')]:
            val=validate_classification('Salida', {'consumption_type':kind,'consumption_detail':subtype})
            self.assertEqual(val['consumption_detail'],subtype)

if __name__ == '__main__':
    unittest.main()
