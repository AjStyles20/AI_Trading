// Images attached to chat messages. They are read in the browser, scaled down
// so uploads stay small, and sent as data URLs; the backend re-validates them.

// `caption` describes where an image came from, e.g. a video frame's timestamp;
// it is added to the message so the model knows what it is looking at.
export type ImageAttachment = { id: string; name: string; dataUrl: string; caption?: string };

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

// Videos: no common chat model watches video, so a few evenly spaced frames are
// taken in the browser and sent as images. The video itself never leaves the
// computer, and its sound is not analysed.
export const ACCEPTED_VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/quicktime'];
export const MAX_VIDEO_BYTES = 500 * 1024 * 1024;
export const VIDEO_FRAME_COUNT = 4;

export const checkVideoFile = (file: File): string | null => {
  if (!ACCEPTED_VIDEO_TYPES.includes(file.type)) return `${file.name}: only MP4, WebM or MOV videos can be attached.`;
  if (file.size > MAX_VIDEO_BYTES) return `${file.name}: larger than ${MAX_VIDEO_BYTES / (1024 * 1024)} MB.`;
  return null;
};

export const formatClipTime = (seconds: number): string => {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
};

// Frame times centred in equal slices of the clip, e.g. 4 frames of a 40 s
// clip at 5, 15, 25 and 35 s.
export const frameTimes = (duration: number, count = VIDEO_FRAME_COUNT): number[] =>
  Number.isFinite(duration) && duration > 0
    ? Array.from({ length: count }, (_, i) => (duration * (i + 0.5)) / count)
    : [0];

const once = (target: HTMLVideoElement, event: string) => new Promise<void>((resolve, reject) => {
  const done = () => { cleanup(); resolve(); };
  const fail = () => {
    cleanup();
    const reason = target.error?.message;
    reject(new Error(`The video could not be read in this app${reason ? ` (${reason})` : ''}.`));
  };
  const cleanup = () => { target.removeEventListener(event, done); target.removeEventListener('error', fail); };
  target.addEventListener(event, done);
  target.addEventListener('error', fail);
});

export const prepareVideoFrames = async (file: File, count = VIDEO_FRAME_COUNT): Promise<ImageAttachment[]> => {
  const problem = checkVideoFile(file);
  if (problem) throw new Error(problem);
  const url = URL.createObjectURL(file);
  try {
    const video = document.createElement('video');
    video.muted = true;
    video.preload = 'auto';
    const loaded = once(video, 'loadeddata');
    video.src = url;
    await loaded;
    const { width, height } = scaledSize(video.videoWidth, video.videoHeight);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('This browser cannot read video frames.');
    const frames: ImageAttachment[] = [];
    for (const time of frameTimes(video.duration, count)) {
      const seeked = once(video, 'seeked');
      video.currentTime = time;
      await seeked;
      context.drawImage(video, 0, 0, width, height);
      frames.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        name: `${file.name} @ ${formatClipTime(time)}`,
        dataUrl: canvas.toDataURL('image/jpeg', 0.8),
        caption: `Frame from video "${file.name}" at ${formatClipTime(time)}`,
      });
    }
    return frames;
  } finally {
    URL.revokeObjectURL(url);
  }
};

// Text added to a message so the model knows which images are video frames.
export const attachmentCaptionText = (attachments: ImageAttachment[]): string => {
  const captions = attachments.map((attachment, index) => attachment.caption && `Image ${index + 1}: ${attachment.caption}`).filter(Boolean);
  return captions.length > 0
    ? `${captions.join('\n')}\n(These are still frames from a video; its sound was not included.)`
    : '';
};
