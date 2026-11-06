// Tailscale addresses are 100.64.0.0 to 100.127.255.255; the phone gateway only
// listens on one of them (or this computer).
export const isTailscaleAddress = (value: string): boolean => {
  const parts = value.trim().split('.');
  if (parts.length !== 4 || !parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)) return false;
  return Number(parts[0]) === 100 && Number(parts[1]) >= 64 && Number(parts[1]) <= 127;
};
