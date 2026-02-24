import { validateMIMEType } from 'validate-image-type';

export default function (pathToImg): boolean {
  const result = validateMIMEType(pathToImg, {
    allowMimeTypes: ['image/jpeg', 'image/gif', 'image/png', 'image/svg+xml'],
  });
  return result.ok;
}
