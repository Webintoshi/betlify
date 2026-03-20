export const COUPON_STORAGE_KEY = "betlify-coupon-selections";

export type CouponSelection = {
  match_id: string;
  home_team: string;
  away_team: string;
  market_type: string;
  odd: number;
  confidence_score: number;
  ev_percentage: number;
};

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function getCouponSelections(): CouponSelection[] {
  if (!isBrowser()) {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(COUPON_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as CouponSelection[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed;
  } catch {
    return [];
  }
}

export function saveCouponSelections(selections: CouponSelection[]): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(COUPON_STORAGE_KEY, JSON.stringify(selections));
}

export function addCouponSelection(selection: CouponSelection): CouponSelection[] {
  const current = getCouponSelections();
  const exists = current.some((item) => item.match_id === selection.match_id);
  const next = exists
    ? current.map((item) => (item.match_id === selection.match_id ? selection : item))
    : [...current, selection];
  saveCouponSelections(next);
  return next;
}

export function removeCouponSelection(matchId: string): CouponSelection[] {
  const current = getCouponSelections();
  const next = current.filter((item) => item.match_id !== matchId);
  saveCouponSelections(next);
  return next;
}

export function clearCouponSelections(): void {
  saveCouponSelections([]);
}

export function calculateTotalOdds(selections: CouponSelection[]): number {
  if (!selections.length) {
    return 0;
  }
  return Number(selections.reduce((acc, item) => acc * item.odd, 1).toFixed(3));
}
