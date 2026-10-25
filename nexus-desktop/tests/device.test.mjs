import { test } from 'node:test';
import assert from 'node:assert/strict';
const device = await import('../src/services/device.ts').catch(() => ({}));

test('device names are readable for phones, tablets and the desktop window', () => {
  assert.equal(typeof device.deviceName, 'function');
  assert.equal(device.deviceName('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36', false), 'Android · Chrome');
  assert.equal(device.deviceName('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1', false), 'iPhone · Safari');
  assert.equal(device.deviceName('Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0 Mobile Safari/537.36', false), 'Android · Samsung Internet');
  assert.equal(device.deviceName('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0', true), 'Este computador (Windows)');
  assert.equal(device.deviceName('', false), 'Aparelho · Navegador');
});
