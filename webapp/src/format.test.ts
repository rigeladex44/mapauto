import {expect,test} from 'vitest';
import {date,number,statusLabel} from './format';
test('renders explicit job states and absent dates',()=>{expect(statusLabel('failed')).toBe('Gagal');expect(statusLabel('cancelled')).toBe('Dibatalkan');expect(date(null)).toBe('—');expect(number(1000)).toBe('1.000');});
