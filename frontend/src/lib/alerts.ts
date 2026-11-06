export type AlertDirection = 'above' | 'below';

export type PriceAlert = {
  id: number;
  symbol: string;
  asset_type: 'crypto' | 'stock';
  direction: AlertDirection;
  price: number;
  note: string;
  created_at: string;
  triggered_at: string | null;
  triggered_price: number | null;
};

// How often active alerts are checked while the app is open. Quotes come from
// the backend's shared cache, so this adds little load on the data provider.
export const ALERT_CHECK_MS = 30_000;

export const isCrossed = (alert: Pick<PriceAlert, 'direction' | 'price'>, price: number): boolean =>
  Number.isFinite(price) && price > 0 && (alert.direction === 'above' ? price >= alert.price : price <= alert.price);

// A positive finite price typed by the user, or null.
export const parseAlertPrice = (raw: string): number | null => {
  const value = Number(raw.replace(/,/g, '').trim());
  return raw.trim() !== '' && Number.isFinite(value) && value > 0 ? value : null;
};

export const describeAlert = (alert: Pick<PriceAlert, 'symbol' | 'direction' | 'price'>): string =>
  `${alert.symbol} ${alert.direction === 'above' ? 'rises to' : 'falls to'} ${alert.price.toLocaleString(undefined, { maximumFractionDigits: 8 })}`;

// Desktop notification when allowed; returns whether one was shown.
export const notify = (title: string, body: string): boolean => {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return false;
  try {
    new Notification(title, { body });
    return true;
  } catch {
    return false;
  }
};
