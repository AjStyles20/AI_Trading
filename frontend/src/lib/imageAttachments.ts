// Images attached to chat messages. They are read in the browser, scaled down
// so uploads stay small, and sent as data URLs; the backend re-validates them.

export type ImageAttachment = { id: string; name: string; dataUrl: string };

export const MAX_ATTACHMENTS = 4;
export const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
// Largest file accepted before resizing (a big phone photo); the result is far smaller.
export const MAX_SOURCE_BYTES = 25 * 1024 * 1024;
// Longest side after resizing: plenty for a model to read charts and text.
export const MAX_IMAGE_SIDE = 1600;
// Images already this small and within MAX_IMAGE_SIDE are sent unchanged.
const KEEP_ORIGINAL_BYTES = 1.5 * 1024 * 1024;

export const checkImageFile = (file: File): string | null => {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) return `${file.name}: only PNG, JPEG, WebP or GIF images can be attached.`;
  if (file.size > MAX_SOURCE_BYTES) return `${file.name}: larger than ${MAX_SOURCE_BYTES / (1024 * 1024)} MB.`;
  return null;
};

const readAsDataUrl = (file: Blob): Promise<string> => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(reader.error ?? new Error('Could not read the file.'));
  reader.readAsDataURL(file);
});

const loadImage = (src: string): Promise<HTMLImageElement> => new Promise((resolve, reject) => {
  const image = new Image();
  image.onload = () => resolve(image);
  image.onerror = () => reject(new Error('The image could not be opened.'));
  image.src = src;
});

export const scaledSize = (width: number, height: number, maxSide = MAX_IMAGE_SIDE) => {
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
};

// Reads an image file, scaling it to MAX_IMAGE_SIDE and re-encoding it as JPEG
// when it is large; small images keep their original format.
export const prepareImageAttachment = async (file: File): Promise<ImageAttachment> => {
  const problem = checkImageFile(file);
  if (problem) throw new Error(problem);
  const original = await readAsDataUrl(file);
  const image = await loadImage(original);
  const { width, height } = scaledSize(image.naturalWidth, image.naturalHeight);
  let dataUrl = original;
  if (width !== image.naturalWidth || file.size > KEEP_ORIGINAL_BYTES) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('This browser cannot resize images.');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  }
  return { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, name: file.name || 'image', dataUrl };
};
