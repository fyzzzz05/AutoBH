export const appearanceModes = ['system', 'light', 'dark'];
export function normalizeAppearance(mode) { return appearanceModes.includes(mode) ? mode : 'system'; }
export function resolvedAppearance(mode, systemDark) { return mode === 'dark' || (normalizeAppearance(mode) === 'system' && systemDark) ? 'dark' : 'light'; }

// CSS resolves system mode too, so the server-provided preference paints correctly
// before React starts. Native WebKit storage is intentionally nonpersistent.
export function applyAppearance(mode, systemDark, doc = document, native = window.webkit) {
  const preference = normalizeAppearance(mode);
  doc.documentElement.dataset.appearance = preference;
  const dark = resolvedAppearance(preference, systemDark) === 'dark';
  doc.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#15161e' : '#f4f4f7');
  native?.messageHandlers?.appearance?.postMessage(preference);
}
