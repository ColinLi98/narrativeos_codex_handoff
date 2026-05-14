export function shouldUseDemoFallback(path: string): boolean {
  if (path.startsWith('/story/') || path.startsWith('/ops/')) {
    return false;
  }
  return path.startsWith('/demo/');
}
