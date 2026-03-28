export interface NamedEntityLike {
  id?: string | null;
  name?: string | null;
  display_name?: string | null;
  displayName?: string | null;
}

export const CARD_NAME_OVERRIDES: Record<string, string> = {
  Strike_R: "打击",
  Strike_G: "打击",
  Strike_B: "打击",
  Strike_P: "打击",
  Defend_R: "防御",
  Defend_G: "防御",
  Defend_B: "防御",
  Defend_P: "防御",
  Bash: "重击",
  Neutralize: "中和",
  Survivor: "幸存者",
  Zap: "电击",
  Dualcast: "双重施放",
  Eruption: "爆发",
  Vigilance: "警惕",
  "Underhanded Strike": "暗击",
  "Dodge and Roll": "闪避与翻滚",
  "Calculated Gamble": "计算赌注",
  Acrobatics: "杂技",
  "Quick Slash": "快斩",
  "Beam Cell": "光束射线",
  Coolheaded: "冷静头脑",
  "Genetic Algorithm": "遗传算法",
  Stack: "堆栈",
  "Ball Lightning": "球状闪电",
  "Doom and Gloom": "愁云惨淡",
  BootSequence: "启动流程",
  "Boot Sequence": "启动流程",
};

export const RELIC_NAME_OVERRIDES: Record<string, string> = {
  "Burning Blood": "燃烧之血",
  "Ring of the Snake": "蛇之戒指",
  PureWater: "圣水",
  "Pure Water": "圣水",
  "Cracked Core": "破损核心",
  "Juzu Bracelet": "念珠项链",
  "Maw Bank": "巨口储钱罐",
  MawBank: "巨口储钱罐",
  BloodVial: "小血瓶",
  "Blood Vial": "小血瓶",
  MealTicket: "餐券",
  "Meal Ticket": "餐券",
};

export const POTION_NAME_OVERRIDES: Record<string, string> = {};

export const ALL_NAME_OVERRIDES: Record<string, string> = {
  ...CARD_NAME_OVERRIDES,
  ...RELIC_NAME_OVERRIDES,
  ...POTION_NAME_OVERRIDES,
};

const MOJIBAKE_MARKERS = [
  "锟",
  "鎵",
  "闃",
  "閲",
  "涓",
  "骞",
  "鐢",
  "鍙",
  "鐖",
  "璀",
  "鏆",
  "闂",
  "璁",
  "鏉",
  "蹇",
  "鍏",
  "鍐",
  "閬",
  "鍫",
  "铔",
  "鐕",
  "鐮",
  "蹇",
  "宸",
];

const SUSPICIOUS_NAME_PATTERN = /[^A-Za-z0-9\u4E00-\u9FFF\s_\-+.'&:/()（）【】]/;

export function looksGarbledText(value: string | null | undefined): boolean {
  if (value == null) {
    return true;
  }

  const text = value.trim();
  if (!text) {
    return true;
  }
  if (text.includes("\ufffd")) {
    return true;
  }
  if (MOJIBAKE_MARKERS.some((marker) => text.includes(marker))) {
    return true;
  }
  if (SUSPICIOUS_NAME_PATTERN.test(text)) {
    return true;
  }

  for (const ch of text) {
    const codepoint = ch.codePointAt(0) ?? 0;
    if (codepoint >= 0x0590 && codepoint <= 0x08ff) {
      return true;
    }
  }

  return false;
}

export function prettifyIdentifier(value: string | null | undefined): string {
  const text = value?.trim() ?? "";
  if (!text) {
    return "未知";
  }
  if (text.includes(" ")) {
    return text;
  }

  let compact = text.replace(/[_-]+/g, " ").trim();
  compact = compact.replace(/\b([RGBP])\b$/i, "").trim();
  compact = compact.replace(/\s+/g, " ");
  return compact || text;
}

export function resolveKnownName(
  itemId: string | null | undefined,
  rawName: string | null | undefined,
  overrides: Record<string, string>,
): string {
  const id = itemId?.trim() ?? "";
  const name = rawName?.trim() ?? "";

  if (id && overrides[id]) {
    return overrides[id];
  }
  if (name && overrides[name]) {
    return overrides[name];
  }
  if (name && !looksGarbledText(name)) {
    return name;
  }
  if (id) {
    return prettifyIdentifier(id);
  }
  if (name) {
    return prettifyIdentifier(name);
  }
  return "未知";
}

export function buildNameCatalog(items: NamedEntityLike[]): Map<string, string> {
  const catalog = new Map<string, string>();

  for (const item of items) {
    const id = item.id?.trim() ?? "";
    const rawDisplay = (item.display_name ?? item.displayName ?? item.name ?? "").trim();
    if (!rawDisplay || looksGarbledText(rawDisplay)) {
      continue;
    }

    const candidates = [id, rawDisplay, prettifyIdentifier(id), prettifyIdentifier(rawDisplay)];
    for (const candidate of candidates) {
      const key = candidate.trim();
      if (!key) {
        continue;
      }
      catalog.set(key, rawDisplay);
      catalog.set(key.toLowerCase(), rawDisplay);
    }
  }

  return catalog;
}

export function resolveCatalogName(value: string | null | undefined, catalog: Map<string, string>): string | null {
  const text = value?.trim() ?? "";
  if (!text) {
    return null;
  }

  const direct = catalog.get(text) ?? catalog.get(text.toLowerCase());
  if (direct) {
    return direct;
  }

  const pretty = prettifyIdentifier(text);
  return catalog.get(pretty) ?? catalog.get(pretty.toLowerCase()) ?? null;
}
