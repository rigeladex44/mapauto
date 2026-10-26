import unittest
from portal.backend.policy import candidates, parse_niks, parse_stock

class PolicyTests(unittest.TestCase):
    def test_all_type_combinations_and_priority(self):
        for mode, available, expected in [
            ('RT', ['Rumah Tangga'], ['RT']), ('UM', ['Rumah Tangga'], []),
            ('RT & UM', ['Rumah Tangga'], ['RT']), ('RT & UM', ['Usaha Mikro'], ['UM']),
            ('RT & UM', ['Rumah Tangga', 'Usaha Mikro'], ['UM', 'RT']),
            ('RT & UM', ['Pengecer', 'Rumah Tangga', 'Usaha Mikro'], ['UM', 'RT']),
            ('RT & UM', ['Petani Sasaran', 'Nelayan Sasaran', 'Pengecer'], []),
            ('UM', ['Usaha Mikro', 'Pengecer'], ['UM'])]:
            with self.subTest(mode=mode, available=available):
                self.assertEqual(candidates(mode, available), expected)

    def test_validation_preserves_leading_zero_and_deduplicates(self):
        self.assertEqual(parse_niks(['0000000000000001'] * 2), ['0000000000000001'])
        for values in [[], ['123'], ['１２３４５６７８９０１２３４５６'], ['1'*16]*501]:
            with self.assertRaises(ValueError): parse_niks(values)

    def test_stock_zero_is_valid_but_missing_or_conflicting_is_not(self):
        self.assertEqual(parse_stock('Stok Tabung per hari\n0 Tabung'), 0)
        self.assertEqual(parse_stock('Stok 1.234 Tabung'), 1234)
        for text in ['Tidak terbaca', '0 Tabung 18 Tabung']:
            with self.assertRaises(ValueError): parse_stock(text)
