"""Pure customer selection policy; never infer a type from button position."""
import re
from enum import Enum

class Mode(str, Enum):
    RT = 'RT'
    UM = 'UM'
    BOTH = 'RT & UM'

LABELS = {'RT': 'Rumah Tangga', 'UM': 'Usaha Mikro'}

def normalize_type(label):
    value = ' '.join(label.upper().split())
    return {'RUMAH TANGGA': 'RT', 'USAHA MIKRO': 'UM', 'RT': 'RT', 'UM': 'UM'}.get(value)

def candidates(mode, available):
    allowed = ['UM', 'RT'] if mode == Mode.BOTH else [Mode(mode).value]
    found = {normalize_type(t) for t in available}
    return [t for t in allowed if t in found]

def parse_niks(values):
    if not 1 <= len(values) <= 500:
        raise ValueError('Masukkan 1–500 NIK.')
    if any(not isinstance(v, str) or not re.fullmatch(r'[0-9]{16}', v) for v in values):
        raise ValueError('Setiap NIK harus tepat 16 digit angka.')
    return list(dict.fromkeys(values))

def parse_stock(text):
    values = set(re.findall(r'(?<![\d.,])([0-9]+(?:\.[0-9]{3})*)\s*Tabung\b', text, re.I))
    if len(values) != 1:
        raise ValueError('Angka stok tidak terbaca secara pasti.')
    return int(values.pop().replace('.', ''))
