/** "Lembrar neste aparelho": credencial de longa duração guardada só neste navegador, por origem, e trocada a cada uso. */
export interface RememberedDevice { id: number; token: string }
const KEY = 'nexus-wolfs:aparelho';

export function loadDevice(): RememberedDevice | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<RememberedDevice>;
    return typeof parsed.id === 'number' && typeof parsed.token === 'string' && parsed.token.length >= 20 ? { id: parsed.id, token: parsed.token } : null;
  } catch { return null; }
}

export function saveDevice(device: RememberedDevice) {
  try { localStorage.setItem(KEY, JSON.stringify(device)); } catch { /* Sem armazenamento, a sessão vale só até fechar. */ }
}

export function clearDevice() {
  try { localStorage.removeItem(KEY); } catch { /* nada a limpar */ }
}

/** Nome legível do aparelho a partir do User-Agent, para a lista "Aparelhos lembrados". */
export function deviceName(userAgent: string, onThisComputer: boolean): string {
  const ua = userAgent || '';
  const system = /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS X/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : 'Aparelho';
  const browser = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /SamsungBrowser\//.test(ua) ? 'Samsung Internet' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Navegador';
  if (onThisComputer) return `Este computador (${system})`;
  return `${system} · ${browser}`;
}
