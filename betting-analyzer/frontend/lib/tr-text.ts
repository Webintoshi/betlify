export const TR = {
  sofaScoreCache: "SofaScore Cache",
  betlify: "Betlify",
  teams: "Tak\u0131mlar",
  team: "Tak\u0131m",
  teamFilter: "Tak\u0131m Filtresi",
  teamSearch: "Tak\u0131m Ara",
  teamDetail: "Tak\u0131m Detay\u0131",
  teamProfile: "Tak\u0131m Profili",
  backToTeams: "Tak\u0131mlara D\u00f6n",
  country: "\u00dclke",
  countryLabel: "\u00dclkesi",
  league: "Lig",
  limit: "Limit",
  allLeagues: "T\u00fcm Ligler",
  allCountries: "T\u00fcm \u00dclkeler",
  totalTeams: "Toplam",
  statusReady: "Haz\u0131r",
  statusPending: "Bekliyor",
  statusStale: "G\u00fcncellenecek",
  coach: "Teknik Direkt\u00f6r",
  unknown: "Bilinmiyor",
  unknownLeague: "Bilinmeyen Lig",
  get: "Getir",
  teamsSubtitle: "Lig bazl\u0131 tak\u0131m dizini, logo, \u00fclke ve teknik direkt\u00f6r profili",
  loadErrorTitle: "Tak\u0131m verisi \u015fu anda y\u00fcklenemedi",
  loadErrorBodyPrefix: "Backend ba\u011flant\u0131s\u0131 veya ortam de\u011fi\u015fkeni hatas\u0131 var. Ayr\u0131nt\u0131:",
  noTeamsTitle: "Filtreye uygun tak\u0131m bulunamad\u0131",
  noTeamsBody: "Lig veya \u00fclke filtresini gev\u015fetip tekrar deneyin",
  teamDataUnavailable: "Tak\u0131m verisi al\u0131namad\u0131",
  genericInfo: "Genel Bilgiler",
  genericInfoBody: "Bu sayfa tak\u0131m kart\u0131ndaki temel bilgileri sistem i\u00e7inden g\u00f6sterir. Kullan\u0131c\u0131y\u0131 d\u0131\u015f kayna\u011fa g\u00f6ndermiyoruz.",
  systemRecord: "Sistem Kayd\u0131",
  systemRecordBody: "Tak\u0131m verisi SofaScore cache katman\u0131ndan al\u0131n\u0131yor ve sistem i\u00e7inde saklan\u0131yor.",
  sofaScoreId: "SofaScore ID",
  status: "Durum",
  lastSynced: "Son E\u015fitleme",
  notYet: "Hen\u00fcz yok",
} as const;

export function decodeUnicodeEscapes(value: string): string {
  return value.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) =>
    String.fromCharCode(Number.parseInt(hex, 16))
  );
}

export function repairDisplayText(value?: string | null): string {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }

  const unescaped = decodeUnicodeEscapes(text);
  if (!/[\u00C3\u00C4\u00C5]/.test(unescaped)) {
    return unescaped;
  }

  try {
    const bytes = Uint8Array.from(Array.from(unescaped), (character) => character.charCodeAt(0) & 0xff);
    const repaired = new TextDecoder("utf-8").decode(bytes).trim();
    return repaired || unescaped;
  } catch {
    return unescaped;
  }
}
