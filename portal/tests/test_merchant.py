import unittest
from portal.backend.merchant import Merchant, MerchantError

class Locator:
    def __init__(self, label, page): self.label, self.page = label, page
    async def all(self): return [self] if self.label in self.page.available else []
    async def is_visible(self): return True
    async def click(self): self.page.chosen = self.label

class Page:
    def __init__(self, available): self.available, self.chosen = available, None
    def get_by_text(self, label, exact=True): return Locator(label, self)
    def get_by_role(self, *args, **kwargs): return Locator('continue', self)

class FixtureMerchant(Merchant):
    def __init__(self, states, available, active_type):
        super().__init__(); self.states=iter(states); self.page=Page(available); self.active_type=active_type
    async def lookup(self, nik): return next(self.states)
    async def wait_nik_state(self, allow_choice=True): return 'sale'
    async def sale_type(self): return self.active_type
    async def text(self): return 'melebihi batas kewajaran' if self.page.chosen=='Usaha Mikro' else ''
    async def one(self, loc): return loc

async def emit(stage): pass
class MerchantTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_type_um_limit_reopens_and_falls_back_to_rt(self):
        m=FixtureMerchant(['choice','choice'], ['Rumah Tangga','Usaha Mikro','Pengecer'], 'RT')
        result=await m.prepare('0'*16,'RT & UM',emit)
        self.assertEqual(result['status'],'Siap ditinjau'); self.assertEqual(result['type'],'RT')
        self.assertIn('UM limit',result['reason'])
    async def test_single_type_mismatch_is_skipped(self):
        m=FixtureMerchant(['sale'],[], 'RT')
        self.assertEqual((await m.prepare('0'*16,'UM',emit))['status'],'Dilewati')
    async def test_unknown_type_never_continues(self):
        m=FixtureMerchant(['choice'],['Pengecer'],None)
        self.assertEqual((await m.prepare('0'*16,'RT & UM',emit))['status'],'Dilewati')
    async def test_wrong_active_type_stops(self):
        m=FixtureMerchant(['choice'],['Rumah Tangga'],'UM')
        with self.assertRaises(MerchantError): await m.prepare('0'*16,'RT',emit)
    async def test_direct_um_is_inspected_not_marked_successful(self):
        m=FixtureMerchant(['sale'],[], 'UM')
        self.assertEqual((await m.prepare('0'*16,'RT & UM',emit))['status'],'Siap ditinjau')
