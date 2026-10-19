// Native select menus can keep :focus-visible after a mouse selection. Track
// navigation intent so mouse clicks don't leave keyboard rings behind.
export function installInputModality(doc = document) {
  doc.documentElement.dataset.input = 'pointer';
  doc.addEventListener('pointerdown', () => { doc.documentElement.dataset.input = 'pointer'; }, true);
  doc.addEventListener('keydown', (event) => {
    if (['Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', ' '].includes(event.key)) {
      doc.documentElement.dataset.input = 'keyboard';
    }
  }, true);
}
