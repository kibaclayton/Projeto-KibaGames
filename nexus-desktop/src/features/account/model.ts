/** Regras puras da conta: recorte do avatar e validação da troca de senha. Sem DOM, testável no Node. */
export interface CropState { viewport: number; naturalWidth: number; naturalHeight: number; zoom: number; offsetX: number; offsetY: number }
export interface CropRect { x: number; y: number; width: number; height: number }

export const MIN_ZOOM = 1, MAX_ZOOM = 4;
export const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
export const MAX_AVATAR_BYTES = 10 * 1024 * 1024;

/** Escala que faz a imagem cobrir o quadro quadrado inteiro no zoom 1. */
export function coverScale(viewport: number, naturalWidth: number, naturalHeight: number) {
  return viewport / Math.min(naturalWidth, naturalHeight);
}

export function displayScale(state: CropState) { return coverScale(state.viewport, state.naturalWidth, state.naturalHeight) * state.zoom; }

/** Mantém a imagem sempre cobrindo o quadro: não pode sobrar fundo em nenhuma borda. */
export function clampOffset(state: CropState): { offsetX: number; offsetY: number } {
  const scale = displayScale(state);
  const width = state.naturalWidth * scale, height = state.naturalHeight * scale;
  return { offsetX: Math.min(0, Math.max(state.viewport - width, state.offsetX)), offsetY: Math.min(0, Math.max(state.viewport - height, state.offsetY)) };
}

export function centeredOffset(viewport: number, naturalWidth: number, naturalHeight: number, zoom = 1) {
  const scale = coverScale(viewport, naturalWidth, naturalHeight) * zoom;
  return { offsetX: (viewport - naturalWidth * scale) / 2, offsetY: (viewport - naturalHeight * scale) / 2 };
}

/** Muda o zoom mantendo fixo o ponto da imagem que está no centro do quadro. */
export function zoomAround(state: CropState, zoom: number): CropState {
  const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
  const before = displayScale(state), after = displayScale({ ...state, zoom: next });
  const centerX = (state.viewport / 2 - state.offsetX) / before, centerY = (state.viewport / 2 - state.offsetY) / before;
  const moved = { ...state, zoom: next, offsetX: state.viewport / 2 - centerX * after, offsetY: state.viewport / 2 - centerY * after };
  return { ...moved, ...clampOffset(moved) };
}

/** Retângulo em pixels da imagem original (já orientada), como o serviço espera em x, y, largura e altura. */
export function cropRect(state: CropState): CropRect {
  const scale = displayScale(state);
  const { offsetX, offsetY } = clampOffset(state);
  let size = Math.round(state.viewport / scale);
  size = Math.max(1, Math.min(size, state.naturalWidth, state.naturalHeight));
  const x = Math.min(Math.max(0, Math.round(-offsetX / scale)), state.naturalWidth - size);
  const y = Math.min(Math.max(0, Math.round(-offsetY / scale)), state.naturalHeight - size);
  return { x, y, width: size, height: size };
}

export function validateAvatarFile(file: { type: string; size: number }): string | null {
  if (!AVATAR_TYPES.includes(file.type)) return 'Escolha uma imagem JPEG, PNG ou WebP.';
  if (file.size > MAX_AVATAR_BYTES) return 'A imagem precisa ter no máximo 10 MB.';
  return null;
}

export function validatePasswordChange(current: string, next: string, confirmation: string): string | null {
  if (!current) return 'Informe a senha atual.';
  if (next.length < 8) return 'A nova senha precisa ter pelo menos 8 caracteres.';
  if (next.length > 256) return 'A nova senha pode ter no máximo 256 caracteres.';
  if (next === current) return 'A nova senha precisa ser diferente da atual.';
  if (confirmation !== next) return 'A confirmação da nova senha não confere.';
  return null;
}
