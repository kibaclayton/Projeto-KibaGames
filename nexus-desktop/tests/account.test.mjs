import { test } from 'node:test';
import assert from 'node:assert/strict';
const account = await import('../src/features/account/model.ts').catch(() => ({}));

test('a landscape photo covers the square frame and the centered crop is the middle square', () => {
  assert.equal(typeof account.cropRect, 'function');
  const base = { viewport: 280, naturalWidth: 1200, naturalHeight: 800, zoom: 1 };
  const state = { ...base, ...account.centeredOffset(280, 1200, 800) };
  assert.deepEqual(account.cropRect(state), { x: 200, y: 0, width: 800, height: 800 });
  const portrait = { viewport: 280, naturalWidth: 600, naturalHeight: 900, zoom: 1, ...account.centeredOffset(280, 600, 900) };
  assert.deepEqual(account.cropRect(portrait), { x: 0, y: 150, width: 600, height: 600 });
});

test('panning is clamped so the frame never shows empty background', () => {
  const state = { viewport: 280, naturalWidth: 1200, naturalHeight: 800, zoom: 1, offsetX: 500, offsetY: -900 };
  const clamped = account.clampOffset(state);
  assert.equal(clamped.offsetX, 0, 'cannot drag past the left edge');
  assert.equal(clamped.offsetY, 0, 'image height equals the frame, so vertical pan is locked');
  const dragged = account.clampOffset({ ...state, offsetX: -5000 });
  assert.equal(Math.round(dragged.offsetX), -140, 'rightmost position keeps the frame covered');
  assert.deepEqual(account.cropRect({ ...state, offsetX: -5000 }), { x: 400, y: 0, width: 800, height: 800 });
});

test('zooming keeps the frame center fixed and shrinks the crop square', () => {
  const start = { viewport: 280, naturalWidth: 1200, naturalHeight: 800, zoom: 1, ...account.centeredOffset(280, 1200, 800) };
  const zoomed = account.zoomAround(start, 2);
  assert.equal(zoomed.zoom, 2);
  assert.deepEqual(account.cropRect(zoomed), { x: 400, y: 200, width: 400, height: 400 });
  assert.equal(account.zoomAround(start, 9).zoom, account.MAX_ZOOM);
  assert.equal(account.zoomAround(zoomed, 0.2).zoom, account.MIN_ZOOM);
  const back = account.zoomAround(zoomed, 1);
  assert.deepEqual(account.cropRect(back), account.cropRect(start));
});

test('the crop never exceeds the image bounds even after rounding', () => {
  const tiny = { viewport: 280, naturalWidth: 301, naturalHeight: 299, zoom: 1.37, offsetX: -3.2, offsetY: -0.4 };
  const rect = account.cropRect(tiny);
  assert.ok(rect.x >= 0 && rect.y >= 0);
  assert.ok(rect.x + rect.width <= 301 && rect.y + rect.height <= 299, JSON.stringify(rect));
  assert.equal(rect.width, rect.height);
});

test('avatar files are limited to the formats and size the service accepts', () => {
  assert.equal(account.validateAvatarFile({ type: 'image/png', size: 1024 }), null);
  assert.match(account.validateAvatarFile({ type: 'image/gif', size: 1024 }), /JPEG, PNG ou WebP/);
  assert.match(account.validateAvatarFile({ type: 'image/jpeg', size: 10 * 1024 * 1024 + 1 }), /10 MB/);
});

test('password change validation mirrors the service rules before any request is sent', () => {
  assert.equal(account.validatePasswordChange('atual-123', 'nova-senha-456', 'nova-senha-456'), null);
  assert.match(account.validatePasswordChange('', 'nova-senha-456', 'nova-senha-456'), /senha atual/);
  assert.match(account.validatePasswordChange('atual-123', 'curta', 'curta'), /8 caracteres/);
  assert.match(account.validatePasswordChange('atual-123', 'atual-123', 'atual-123'), /diferente/);
  assert.match(account.validatePasswordChange('atual-123', 'nova-senha-456', 'outra'), /confirmação/i);
});
