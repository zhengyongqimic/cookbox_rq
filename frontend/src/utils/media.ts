export const resolveMediaUrl = (path?: string | null): string | null => {
  if (!path) {
    return null;
  }

  if (/^https?:\/\//i.test(path) || path.startsWith('data:') || path.startsWith('blob:')) {
    return path;
  }

  if (path.startsWith('/')) {
    return path;
  }

  return `/${path}`;
};
