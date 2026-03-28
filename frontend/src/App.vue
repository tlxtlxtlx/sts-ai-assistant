<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  ALL_NAME_OVERRIDES,
  CARD_NAME_OVERRIDES,
  POTION_NAME_OVERRIDES,
  RELIC_NAME_OVERRIDES,
  buildNameCatalog,
  looksGarbledText,
  prettifyIdentifier,
  resolveCatalogName,
  resolveKnownName,
} from "./nameResolver";

interface CardView {
  id: string;
  name: string;
  display_name: string;
  upgrades: number;
  cost: number | null;
  type: string | null;
  rarity: string | null;
  price: number | null;
  choice_index: number | null;
}

interface RelicView {
  id: string;
  name: string;
  counter: number | null;
  price: number | null;
  choice_index: number | null;
}

interface PotionView {
  id: string;
  name: string;
  price: number | null;
  choice_index: number | null;
}

interface CardRewardView {
  cards: CardView[];
  bowl_available: boolean;
  skip_available: boolean;
}

interface ShopView {
  cards: CardView[];
  relics: RelicView[];
  potions: PotionView[];
  purge_available: boolean;
  purge_cost: number | null;
}

interface RelicRewardView {
  relics: RelicView[];
  source?: string | null;
  sapphire_key_available?: boolean;
  linked_relic?: RelicView | null;
}

interface ScreenNormalized {
  screen_type: string;
  card_reward?: CardRewardView;
  shop?: ShopView;
  relic_reward?: RelicRewardView;
  combat?: {
    hand: CombatCardView[];
    monsters: CombatMonsterView[];
    energy: number | null;
  };
}

interface CombatCardView {
  id: string;
  name: string;
  display_name?: string;
  cost: number | null;
  type: string | null;
  is_playable?: boolean | null;
}

interface CombatMonsterView {
  id?: string | null;
  name?: string | null;
  current_hp?: number | null;
  max_hp?: number | null;
  intent?: string | null;
  intent_damage?: number | null;
  intent_hits?: number | null;
  block?: number | null;
}

interface DeckBreakdownItem {
  id: string;
  display_name: string;
  copies: number;
  upgrades: number;
}

interface LatestState {
  in_game: boolean;
  ready_for_command: boolean;
  available_commands: string[];
  character_class: string | null;
  ascension_level: number | null;
  floor: number | null;
  act: number | null;
  gold: number | null;
  current_hp: number | null;
  max_hp: number | null;
  deck_size: number;
  deck_breakdown: DeckBreakdownItem[];
  relics: RelicView[];
  deck: CardView[];
  screen: {
    screen_type: string;
    screen_state?: Record<string, unknown>;
    normalized: ScreenNormalized;
  };
}

interface Recommendation {
  screen_type: string;
  suggested_action: string;
  primary_target: string | null;
  build_direction: string | null;
  reasoning: string;
  alternatives: string[];
  raw_response?: Record<string, unknown>;
}

interface AssistantReply {
  mode: "analysis" | "chat";
  conclusion: string;
  reasons: string[];
  alternatives: string[];
  build_direction: string | null;
  source: "auto" | "web" | "ingame";
  created_at: string;
  raw_response?: Record<string, unknown>;
}

interface ChatHistoryItem {
  question: string;
  reply: AssistantReply;
  created_at: string;
}

interface AssistantState {
  session_id: string | null;
  latest_analysis: AssistantReply | null;
  chat_history: ChatHistoryItem[];
  started_at: string | null;
  updated_at: string | null;
  memory_enabled: boolean;
}

interface BuildProfile {
  name: string;
  rating: string;
  tier_label?: string;
  score: number;
  summary: string;
  core_cards: string[];
  support_cards: string[];
  missing_pieces: string[];
  strengths: string[];
  risks: string[];
  next_picks: string[];
  archetype_key?: string;
  source_tags?: string[];
  community_summary?: string | null;
  community_sources?: CommunitySourceView[];
  alternatives?: BuildOption[];
  route_stage?: string | null;
  two_fight_goal?: string[];
  pivot_triggers?: string[];
  avoid_now?: string[];
}

interface BuildOption {
  key: string;
  name: string;
  rating: string;
  tier_label?: string;
  score: number;
  summary: string;
  core_cards: string[];
  support_cards: string[];
  missing_pieces: string[];
  strengths: string[];
  risks: string[];
  next_picks: string[];
  pivot_reason: string;
  source_tags?: string[];
  community_summary?: string | null;
  community_sources?: CommunitySourceView[];
  recommended_now?: boolean;
}

interface CommunitySourceView {
  source_id?: string;
  title: string;
  url: string;
  publisher: string;
  published_at: string;
  summary: string;
  excerpt?: string;
  raw_status: string;
}

interface ApiState {
  updated_at: string | null;
  latest_state: LatestState | null;
  latest_recommendation: Recommendation | null;
  build_profile?: BuildProfile | null;
  assistant: AssistantState;
  diagnostics?: {
    backend_ready: boolean;
    llm_configured: boolean;
    last_state_at: string | null;
    last_screen_type: string | null;
    recommendation_source: string | null;
    recommendation_action: string | null;
    has_combat_data: boolean;
    next_step: string;
  };
}

const API_BASE = (import.meta.env.VITE_STS_API_BASE as string | undefined) ?? "http://127.0.0.1:8765";

const loading = ref(true);
const fetchError = ref<string | null>(null);
const submitError = ref<string | null>(null);
const apiState = ref<ApiState | null>(null);
const lastFetchAt = ref<string | null>(null);
const chatInput = ref("");
const analyzeLoading = ref(false);
const chatLoading = ref(false);

let timer: number | null = null;


const latestState = computed(() => apiState.value?.latest_state ?? null);
const latestRecommendation = computed(() => apiState.value?.latest_recommendation ?? null);
const buildProfile = computed<BuildProfile | null>(() => apiState.value?.build_profile ?? null);
const buildAlternatives = computed<BuildOption[]>(() => buildProfile.value?.alternatives ?? []);
const buildCommunitySources = computed<CommunitySourceView[]>(() => buildProfile.value?.community_sources ?? []);
const localizedNameCatalog = computed(() => {
  const items: Array<{ id?: string | null; name?: string | null; display_name?: string | null }> = [];
  const state = latestState.value;
  if (!state) {
    return buildNameCatalog(items);
  }

  items.push(...state.deck);
  items.push(...state.deck_breakdown);
  items.push(...state.relics);
  const rewardCards = state.screen.normalized.card_reward?.cards ?? [];
  const shopCards = state.screen.normalized.shop?.cards ?? [];
  const shopRelics = state.screen.normalized.shop?.relics ?? [];
  const shopPotions = state.screen.normalized.shop?.potions ?? [];
  const combatCards = state.screen.normalized.combat?.hand ?? [];

  items.push(...rewardCards, ...shopCards, ...shopRelics, ...shopPotions, ...combatCards);
  return buildNameCatalog(items);
});
const assistantState = computed<AssistantState | null>(() => apiState.value?.assistant ?? null);
const diagnostics = computed(() => apiState.value?.diagnostics ?? null);
const latestAnalysis = computed<AssistantReply | null>(() => assistantState.value?.latest_analysis ?? null);
const normalizedScreen = computed(() => latestState.value?.screen.normalized ?? null);
const rawScreenState = computed<Record<string, unknown> | null>(() => {
  const value = latestState.value?.screen.screen_state;
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return null;
});
const connectionLabel = computed(() => {
  if (fetchError.value) {
    return "连接异常";
  }
  if (!latestState.value) {
    return "等待连接";
  }
  return "已连接";
});

const currentScreenLabel = computed(() => screenLabel(latestState.value?.screen.screen_type ?? ""));
const currentTarget = computed(() => activeRecommendation.value?.primary_target ?? latestRecommendation.value?.primary_target ?? null);
const latestAnalysisTitle = computed(() => {
  if (!latestAnalysis.value) {
    return "还没有顾问结果";
  }
  return latestAnalysis.value.mode === "chat" ? "最近一次回答" : "最近一次分析";
});
const fallbackAnalysis = computed<AssistantReply | null>(() => {
  const recommendation = latestRecommendation.value;
  if (!recommendation) {
    return null;
  }
  const reasons = recommendation.reasoning
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 4);
  return {
    mode: "analysis",
    conclusion: recommendationConclusion(recommendation),
    reasons: reasons.length >= 2 ? reasons : ["已根据当前局面生成建议。", "建议优先处理眼前最直接的收益。"],
    alternatives: recommendation.alternatives ?? [],
    build_direction: recommendation.build_direction,
    source: "auto",
    created_at: apiState.value?.updated_at ?? "",
  };
});
const activeReply = computed<AssistantReply | null>(() => {
  const fallback = fallbackAnalysis.value;
  const latest = latestAnalysis.value;
  if (!latest) {
    return fallback;
  }
  if (!fallback) {
    return latest;
  }
  if (isGenericReply(latest) && !isGenericReply(fallback)) {
    return fallback;
  }
  return latest;
});
const activeRecommendation = computed<Recommendation | null>(() => {
  const replyRaw = activeReply.value?.raw_response;
  const nested = replyRaw?.recommendation;
  if (nested && typeof nested === "object") {
    return nested as Recommendation;
  }
  return latestRecommendation.value;
});
const chatHistory = computed(() => assistantState.value?.chat_history ?? []);
const displayAlternatives = computed(() => {
  const unique = new Set<string>();
  for (const item of activeReply.value?.alternatives ?? []) {
    const display = resolveLooseName(item) ?? resolveCatalogName(item, localizedNameCatalog.value) ?? item.trim();
    if (display) {
      unique.add(display);
    }
  }
  return [...unique];
});
const recommendationActionLabel = computed(() => actionLabel(activeRecommendation.value?.suggested_action ?? null));
const recommendationTargetLabel = computed(() => {
  const recommendation = activeRecommendation.value;
  if (!recommendation) {
    return "--";
  }
  const resolved = resolveLooseName(recommendation.primary_target) ?? resolveCatalogName(recommendation.primary_target, localizedNameCatalog.value) ?? recommendation.primary_target;
  if (resolved) {
    return resolved;
  }
  return inferRecommendationTarget() ?? "待后端刷新";
});
const recommendationBuildDirection = computed(() => activeReply.value?.build_direction ?? activeRecommendation.value?.build_direction ?? null);
const recommendationRaw = computed<Record<string, unknown>>(() => {
  const raw = activeRecommendation.value?.raw_response;
  return raw && typeof raw === "object" ? raw : {};
});
const recommendationConfidence = computed(() => {
  const value = recommendationRaw.value.confidence;
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.min(1, value));
  }
  return null;
});
const recommendationConfidenceLabel = computed(() => {
  const value = recommendationConfidence.value;
  if (value === null) {
    return "待判断";
  }
  const percent = Math.round(value * 100);
  if (percent >= 85) {
    return `很稳 (${percent}%)`;
  }
  if (percent >= 70) {
    return `可直接照做 (${percent}%)`;
  }
  return `可做但要看后手 (${percent}%)`;
});
const recommendationOpportunityCost = computed(() => {
  const value = recommendationRaw.value.opportunity_cost;
  return typeof value === "string" && value.trim() ? value.trim() : "当前没有额外机会成本提示。";
});
const recommendationFitLabel = computed(() => {
  const value = recommendationRaw.value.fit_label;
  return typeof value === "string" && value.trim() ? value.trim() : "待判断";
});
const recommendationRouteAfterPick = computed(() => {
  const value = recommendationRaw.value.route_after_pick;
  return typeof value === "string" && value.trim() ? value.trim() : "待补充";
});
const recommendationLearningRule = computed(() => {
  const value = recommendationRaw.value.learning_rule;
  return typeof value === "string" && value.trim() ? value.trim() : "前几层先拿能立刻帮你稳住回合的牌。";
});
const recommendationFillsGap = computed(() => {
  const value = recommendationRaw.value.fills_gap;
  return typeof value === "string" && value.trim() ? value.trim() : "这次推荐主要是在补当前最直接的短板。";
});
const recommendationSafeDefault = computed(() => {
  const value = recommendationRaw.value.safe_default;
  return typeof value === "string" && value.trim() ? value.trim() : "如果你拿不准，就先照着主推荐走，通常比乱转路线更稳。";
});
const combatSequence = computed<string[]>(() => {
  const value = recommendationRaw.value.play_sequence;
  if (Array.isArray(value)) {
    return value
      .map((item) => resolveLooseName(typeof item === "string" ? item : null) ?? (typeof item === "string" ? item : ""))
      .filter(Boolean);
  }
  return [];
});
const combatBlockThreshold = computed<number | null>(() => {
  const value = recommendationRaw.value.block_threshold;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
});
const combatPotionHint = computed(() => {
  const value = recommendationRaw.value.potion_hint;
  return typeof value === "string" && value.trim() ? value.trim() : "暂无额外药水提醒。";
});
const combatStepOne = computed(() => {
  if (recommendationTargetLabel.value !== "--") {
    return `先用${recommendationTargetLabel.value}起手。`;
  }
  return "先做减伤、减攻或最关键的保命动作。";
});
const combatStepTwo = computed(() => {
  if (combatSequence.value.length >= 2) {
    return `再按${combatSequence.value.slice(1, 3).join(" -> ")}继续打。`;
  }
  if ((combatIncomingDamage.value ?? 0) > 0) {
    return "再把剩余能量优先留给格挡或减伤，先别贪慢热牌。";
  }
  return "再把剩余能量补给高质量输出、成长或过牌。";
});
const combatStepThree = computed(() => combatPotionHint.value);
const combatHand = computed<CombatCardView[]>(() => extractCombatHand(rawScreenState.value));
const combatMonsters = computed<CombatMonsterView[]>(() => extractCombatMonsters(rawScreenState.value));
const combatEnergy = computed<number | null>(() => extractCombatEnergy(rawScreenState.value));
const isCombatScreen = computed(() => (latestState.value?.screen.screen_type ?? "").toUpperCase() === "COMBAT");
const hasCombatContext = computed(() => {
  return isCombatScreen.value;
});
const combatIncomingDamage = computed<number | null>(() => {
  if (!combatMonsters.value.length) {
    return null;
  }
  const total = combatMonsters.value.reduce((sum, monster) => {
    const damage = monster.intent_damage ?? 0;
    const hits = monster.intent_hits ?? 1;
    return sum + damage * Math.max(1, hits);
  }, 0);
  return total > 0 ? total : 0;
});
const statusSummary = computed(() => {
  if (!latestState.value) {
    return "等待游戏状态";
  }
  return `${characterLabel(latestState.value.character_class)} A${valueOrQuestion(latestState.value.ascension_level)} · ${currentScreenLabel.value}`;
});
const guideLead = computed(() => buildUnifiedGuideLead());
const guideNotes = computed(() => buildUnifiedGuideNotes());
const beginnerQuestionTemplates = computed(() => {
  if (hasCombatContext.value) {
    return ["这回合先出哪几张？", "这回合要不要交药？", "我这回合先防还是先打？"];
  }
  return [
    "这层该拿牌还是跳过？",
    "我现在这套牌缺什么？",
    "接下来两场我该找什么？",
    "为什么这次更推荐删牌？",
    "这回合先出哪几张？",
  ];
});
const chatPlaceholder = computed(() => "例如：这张牌为什么值得拿？这回合先打哪张？");
const quickGuideTitle = computed(() => {
  if (fetchError.value) {
    return "先连上本地后端";
  }
  if (!latestState.value) {
    return "先让游戏推送状态";
  }
  if (!diagnostics.value?.llm_configured) {
    return "先把模型配置好";
  }
  return "现在可以直接用了";
});
const quickGuideSteps = computed(() => {
  if (fetchError.value) {
    return [
      "确认后端已启动，且 http://127.0.0.1:8765/api/health 能打开。",
      "如果网页已开很久，先刷新页面。",
      "如果还是失败，重启 scripts/start_all_local.ps1。",
    ];
  }
  if (!latestState.value) {
    return [
      "启动游戏并启用 BaseMod 与 Communication Mod。",
      "确认 Communication Mod 的 command= 指向本项目的 start_backend.cmd。",
      "进入一局游戏后等待 1 到 2 秒，再点刷新状态。",
    ];
  }
  if (!diagnostics.value?.llm_configured) {
    return [
      "编辑 config/app_config.local.json。",
      "填入 OpenAI 兼容接口的 base_url、api_key、model。",
      "重启后端后再点一键分析。",
    ];
  }
  return [
    diagnostics.value?.next_step ?? "状态链路正常，可以直接分析或提问。",
    "想看局面建议就点一键分析。",
    "想问更细的问题就直接在下面聊天框提问。",
  ];
});
const canSendChat = computed(() => chatInput.value.trim().length > 0 && !chatLoading.value);

async function refreshState() {
  try {
    const response = await fetch(`${API_BASE}/api/state`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    apiState.value = (await response.json()) as ApiState;
    fetchError.value = null;
    lastFetchAt.value = new Date().toLocaleTimeString();
  } catch (error) {
    fetchError.value = error instanceof Error ? error.message : "Unknown error";
  } finally {
    loading.value = false;
  }
}

async function analyzeCurrentState() {
  analyzeLoading.value = true;
  submitError.value = null;
  try {
    const response = await fetch(`${API_BASE}/api/assistant/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        source: "web",
        focus: currentScreenLabel.value,
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    await response.json();
    await refreshState();
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : "Unknown error";
  } finally {
    analyzeLoading.value = false;
  }
}

async function sendChat(prefilledMessage?: string) {
  const message = (prefilledMessage ?? chatInput.value).trim();
  if (!message) {
    return;
  }
  chatLoading.value = true;
  submitError.value = null;
  try {
    const response = await fetch(`${API_BASE}/api/assistant/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        source: "web",
        message,
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    chatInput.value = "";
    await response.json();
    await refreshState();
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : "Unknown error";
  } finally {
    chatLoading.value = false;
  }
}

function handleSendChat() {
  void sendChat();
}

function useQuestionTemplate(template: string) {
  chatInput.value = template;
}

function startPolling() {
  void refreshState();
  timer = window.setInterval(() => {
    void refreshState();
  }, 2500);
}

function stopPolling() {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
}

function screenLabel(value: string): string {
  const screen = value.toUpperCase();
  const labels: Record<string, string> = {
    CARD_REWARD: "卡牌奖励",
    SHOP: "商店",
    SHOP_SCREEN: "商店",
    MAP: "地图",
    EVENT: "事件",
    COMBAT: "战斗",
    BOSS_REWARD: "Boss遗物",
    COMBAT_REWARD: "战斗奖励",
    TREASURE: "宝箱",
    CHEST: "宝箱",
    REST: "篝火",
    UNKNOWN: "未知界面",
  };
  return labels[screen] ?? value;
}

function characterLabel(value: string | null): string {
  const labels: Record<string, string> = {
    IRONCLAD: "铁甲战士",
    THE_SILENT: "静默猎手",
    DEFECT: "故障机器人",
    WATCHER: "观者",
  };
  if (!value) {
    return "未知角色";
  }
  return labels[value] ?? value;
}

function valueOrQuestion(value: number | null): string {
  return value === null ? "?" : String(value);
}

function recommendationConclusion(recommendation: Recommendation): string {
  const action = recommendation.suggested_action.toUpperCase();
  const target = resolveLooseName(recommendation.primary_target) ?? resolveCatalogName(recommendation.primary_target, localizedNameCatalog.value) ?? recommendation.primary_target;
  if (action === "TAKE") {
    if ((normalizedScreen.value?.relic_reward?.relics?.length ?? 0) > 0 || target === "蓝钥匙") {
      return target ? `这次遗物选择优先拿${target}。` : "这次遗物选择建议直接拿。";
    }
    return target ? `这次奖励优先拿${target}。` : "这次奖励建议拿牌。";
  }
  if (action === "SKIP") {
    return "这次奖励更适合跳过。";
  }
  if (action === "BOWL") {
    return "这次更适合拿汤提高容错。";
  }
  if (action === "BUY_CARD") {
    return target ? `商店里优先买${target}。` : "商店里优先买牌。";
  }
  if (action === "BUY_RELIC") {
    return target ? `商店里优先买${target}。` : "商店里优先买遗物。";
  }
  if (action === "BUY_POTION") {
    return target ? `商店里可以补${target}。` : "商店里可以补药水。";
  }
  if (action === "REMOVE") {
    return target ? `这家商店优先删掉${target}。` : "这家商店优先考虑删牌。";
  }
  if (action === "LEAVE") {
    return "这家商店可以先不花钱。";
  }
  if (action === "LLM_NOT_CONFIGURED") {
    return "当前还没有配置模型，助手先展示局面摘要。";
  }
  if (action === "PLAY_SEQUENCE") {
    return target ? `这回合先从${target}起手。` : "这回合先按减伤优先顺序出牌。";
  }
  return target ? `建议优先考虑${target}。` : "建议先走保守线。";
}

function isGenericReply(reply: AssistantReply): boolean {
  const text = [reply.conclusion, ...reply.reasons].join(" ").toLowerCase();
  const markers = [
    "建议拿牌",
    "当前候选",
    "先走保守线",
    "局面摘要",
    "继续追问",
    "当前未配置模型",
  ];
  return markers.some((marker) => text.includes(marker.toLowerCase()));
}

function actionLabel(action: string | null): string {
  const value = action?.trim().toUpperCase() ?? "";
  const labels: Record<string, string> = {
    TAKE: "拿牌",
    SKIP: "跳过",
    BOWL: "拿汤",
    BUY_CARD: "买牌",
    BUY_RELIC: "买遗物",
    BUY_POTION: "买药水",
    REMOVE: "删牌",
    LEAVE: "离开",
    PLAY_SEQUENCE: "出牌顺序",
    LLM_NOT_CONFIGURED: "等待模型",
  };
  return labels[value] ?? "--";
}

function inferRecommendationTarget(): string | null {
  const recommendation = activeRecommendation.value ?? latestRecommendation.value;
  if (!recommendation) {
    return null;
  }
  const action = recommendation.suggested_action.toUpperCase();
  const relicReward = normalizedScreen.value?.relic_reward;
  const relics = relicReward?.relics ?? [];
  const targetVariants = collectNameVariants([recommendation.primary_target]);
  if (action === "TAKE" && (relics.length > 0 || targetVariants.has("蓝钥匙"))) {
    if (targetVariants.has("蓝钥匙") && relicReward?.sapphire_key_available) {
      return "蓝钥匙";
    }
    const directRelic = relics.find((relic) => {
      const variants = collectNameVariants([relic.id, relic.name, safeRelicDisplayName(relic)]);
      for (const variant of variants) {
        if (targetVariants.has(variant)) {
          return true;
        }
      }
      return false;
    });
    if (directRelic) {
      return safeRelicDisplayName(directRelic);
    }
    if (relics[0]) {
      return safeRelicDisplayName(relics[0]);
    }
  }
  if (action === "TAKE") {
    const cards = normalizedScreen.value?.card_reward?.cards ?? [];
    if (!cards.length) {
      return null;
    }

    const directMatch = cards.find((card) => {
      const variants = collectNameVariants([card.id, card.name, card.display_name, safeCardDisplayName(card)]);
      const targetVariants = collectNameVariants([recommendation.primary_target]);
      for (const variant of variants) {
        if (targetVariants.has(variant)) {
          return true;
        }
      }
      return false;
    });

    return directMatch ? safeCardDisplayName(directMatch) : safeCardDisplayName(cards[0]);
  }
  if (action === "PLAY_SEQUENCE") {
    if (combatSequence.value[0]) {
      return combatSequence.value[0];
    }
    return combatHand.value[0] ? safeCombatCardDisplayName(combatHand.value[0]) : null;
  }
  return null;
}

function describeCurrentAction(): string {
  const action = recommendationActionLabel.value;
  const target = recommendationTargetLabel.value;
  if (action === "--") {
    return "当前还没有稳定建议，先让助手拿到一个可分析的局面。";
  }
  if (target === "--") {
    return `这一步先按“${action}”处理就行。`;
  }
  return `这一步建议你先“${action}”，目标是“${target}”。`;
}

function explainBuildDirection(value: string | null | undefined): string {
  const text = value?.trim() ?? "";
  if (!text) {
    return "当前还没有固定成型流派，先围绕眼前强度和容错来选。";
  }
  if (text.includes("防御") || text.includes("容错")) {
    return `这表示当前更重视少掉血、稳过前几层，后续优先找能挡伤害或让回合更稳定的牌。`;
  }
  if (text.includes("毒")) {
    return `这表示想走持续伤害路线，后面会更偏好上毒、过牌和拖回合的牌。`;
  }
  if (text.includes("敏捷")) {
    return `这表示想把格挡质量做高，后面通常会更重视防守收益和回合稳定性。`;
  }
  if (text.includes("过牌") || text.includes("运转")) {
    return `这表示当前想先把抽牌和手感做顺，后续会更偏好便宜、不卡手、能换牌的选择。`;
  }
  if (text.includes("输出") || text.includes("伤害")) {
    return `这表示当前更想补即时战力，后续选牌会更看重能不能尽快把怪打死。`;
  }
  return `这表示你现在的构筑重心是“${text}”，后续奖励和商店优先围绕这条线来拿。`;
}

function describeRewardTargetForNovice(): string | null {
  const target = recommendationTargetLabel.value;
  const cards = normalizedScreen.value?.card_reward?.cards ?? [];
  const card =
    cards.find((item) => safeCardDisplayName(item) === target)
    ?? cards.find((item) => item.id === activeRecommendation.value?.primary_target);
  if (!card) {
    return null;
  }
  const name = safeCardDisplayName(card);
  const type = (card.type ?? "").toUpperCase();
  if (type === "ATTACK") {
    return `${name}是一张偏输出的牌，价值主要在于帮你更快结束战斗，少挨打。`;
  }
  if (type === "SKILL") {
    return `${name}是一张偏功能或防守的牌，价值主要在于让你的回合更稳，不容易崩。`;
  }
  if (type === "POWER") {
    return `${name}是一张成长牌，战斗拖得越久通常越值，但前期要注意会不会影响当回合节奏。`;
  }
  return `${name}就是这次建议优先处理的目标。`;
}

function buildUnifiedGuideLead(): string {
  if (!latestState.value) {
    return "你可以把这个项目理解成一个会看局面的中文教练，它会告诉你这一步先做什么。";
  }
  if (!latestRecommendation.value) {
    return `你现在在“${currentScreenLabel.value}”界面，先点一次“一键分析当前局面”。`;
  }
  return `${describeCurrentAction()} 如果你还拿不准，先照这个做通常比自己乱选更稳。`;
}

function buildUnifiedGuideNotes(): string[] {
  const notes = [
    `当前是“${currentScreenLabel.value}”阶段，重点不是把所有好东西都拿走，而是先做最不容易出错的决定。`,
    explainBuildDirection(recommendationBuildDirection.value),
  ];
  const rewardTarget = describeRewardTargetForNovice();
  if (rewardTarget) {
    notes.push(rewardTarget);
  }
  if (hasCombatContext.value) {
    notes.push("如果现在在战斗里，先看上面的推荐操作和战斗面板，不要急着把能量随便花完。");
  } else {
    notes.push("如果你还是不确定，就把“推荐目标”和“备选”当作优先级列表，从上往下看。");
  }
  return notes;
}

function resolveDisplayName(
  itemId: string | null | undefined,
  rawName: string | null | undefined,
  overrides: Record<string, string>,
): string {
  const catalogHit = resolveCatalogName(rawName, localizedNameCatalog.value) ?? resolveCatalogName(itemId, localizedNameCatalog.value);
  if (catalogHit) {
    return catalogHit;
  }
  return resolveKnownName(itemId, rawName, overrides);
}

function resolveLooseName(value: string | null | undefined): string | null {
  const text = value?.trim() ?? "";
  if (!text) {
    return null;
  }

  const catalogHit = resolveCatalogName(text, localizedNameCatalog.value);
  if (catalogHit) {
    return catalogHit;
  }
  if (ALL_NAME_OVERRIDES[text]) {
    return ALL_NAME_OVERRIDES[text];
  }
  if (!looksGarbledText(text)) {
    return prettifyIdentifier(text);
  }
  return null;
}

function collectNameVariants(values: Array<string | null | undefined>): Set<string> {
  const variants = new Set<string>();
  for (const value of values) {
    const text = value?.trim() ?? "";
    if (!text) {
      continue;
    }
    variants.add(text);
    const resolved = resolveLooseName(text);
    if (resolved) {
      variants.add(resolved);
    }
    const catalogHit = resolveCatalogName(text, localizedNameCatalog.value);
    if (catalogHit) {
      variants.add(catalogHit);
    }
  }
  return variants;
}

function safeCardDisplayName(card: Pick<CardView, "id" | "display_name" | "name">): string {
  return resolveDisplayName(card.id, card.display_name || card.name, CARD_NAME_OVERRIDES);
}

function safeDeckCardDisplayName(card: DeckBreakdownItem): string {
  return resolveDisplayName(card.id, card.display_name, CARD_NAME_OVERRIDES);
}

function safeRelicDisplayName(relic: Pick<RelicView, "id" | "name">): string {
  return resolveDisplayName(relic.id, relic.name, RELIC_NAME_OVERRIDES);
}

function safePotionDisplayName(potion: Pick<PotionView, "id" | "name">): string {
  return resolveDisplayName(potion.id, potion.name, POTION_NAME_OVERRIDES);
}

function safeCombatCardDisplayName(card: Pick<CombatCardView, "id" | "display_name" | "name">): string {
  return resolveDisplayName(card.id, card.display_name || card.name, CARD_NAME_OVERRIDES);
}

function cardTypeLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    ATTACK: "攻击",
    SKILL: "技能",
    POWER: "能力",
    STATUS: "状态",
    CURSE: "诅咒",
  };
  const text = value?.trim().toUpperCase() ?? "";
  return labels[text] ?? (value?.trim() || "未知类型");
}

function cardRarityLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    BASIC: "基础",
    COMMON: "普通",
    UNCOMMON: "罕见",
    RARE: "稀有",
    SPECIAL: "特殊",
    CURSE: "诅咒",
  };
  const text = value?.trim().toUpperCase() ?? "";
  return labels[text] ?? (value?.trim() || "未知稀有度");
}

function matchesCurrentTarget(values: Array<string | null | undefined>): boolean {
  const targetVariants = collectNameVariants([currentTarget.value]);
  if (!targetVariants.size) {
    return false;
  }

  const valueVariants = collectNameVariants(values);
  for (const candidate of valueVariants) {
    if (targetVariants.has(candidate)) {
      return true;
    }
  }
  return false;
}

function cardMatchesTarget(card: CardView): boolean {
  return matchesCurrentTarget([card.id, card.name, card.display_name, safeCardDisplayName(card)]);
}

function relicMatchesTarget(relic: RelicView): boolean {
  return matchesCurrentTarget([relic.id, relic.name, safeRelicDisplayName(relic)]);
}

function potionMatchesTarget(potion: PotionView): boolean {
  return matchesCurrentTarget([potion.id, potion.name, safePotionDisplayName(potion)]);
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function communityStatusLabel(value: string | null | undefined): string {
  const status = (value ?? "").trim().toLowerCase();
  if (status === "fetched") {
    return "在线抓取";
  }
  if (status === "cache") {
    return "本地缓存";
  }
  return "本地整理";
}

function extractCombatHand(screenState: Record<string, unknown> | null): CombatCardView[] {
  const normalizedCards = latestState.value?.screen.normalized.combat?.hand;
  const cards = Array.isArray(normalizedCards) && normalizedCards.length
    ? normalizedCards
    : findFirstArray(screenState, ["hand", "hand_cards", "cards_in_hand"]);
  return cards
    .map((item) => normalizeCombatCard(item))
    .filter((item): item is CombatCardView => item !== null);
}

function extractCombatMonsters(screenState: Record<string, unknown> | null): CombatMonsterView[] {
  const normalizedMonsters = latestState.value?.screen.normalized.combat?.monsters;
  const monsters = Array.isArray(normalizedMonsters) && normalizedMonsters.length
    ? normalizedMonsters
    : findFirstArray(screenState, ["monsters", "enemies"]);
  return monsters
    .map((item) => normalizeCombatMonster(item))
    .filter((item): item is CombatMonsterView => item !== null);
}

function extractCombatEnergy(screenState: Record<string, unknown> | null): number | null {
  const normalizedEnergy = latestState.value?.screen.normalized.combat?.energy;
  if (typeof normalizedEnergy === "number" && Number.isFinite(normalizedEnergy)) {
    return normalizedEnergy;
  }
  return findFirstNumber(screenState, ["energy", "current_energy", "energy_count", "player_energy", "energy_remaining"]);
}

function normalizeCombatCard(value: unknown): CombatCardView | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const id = typeof raw.id === "string" ? raw.id : "UNKNOWN_CARD";
  const name = typeof raw.name === "string" ? raw.name : id;
  return {
    id,
    name,
    display_name: typeof raw.display_name === "string" ? raw.display_name : name,
    cost: typeof raw.cost === "number" ? raw.cost : Number(raw.cost ?? NaN),
    type: typeof raw.type === "string" ? raw.type : null,
    is_playable: typeof raw.is_playable === "boolean" ? raw.is_playable : null,
  };
}

function normalizeCombatMonster(value: unknown): CombatMonsterView | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const isGone = raw.is_gone === true || raw.escaped === true;
  const currentHp = coerceNumber(raw.current_hp);
  if (isGone || (currentHp !== null && currentHp <= 0)) {
    return null;
  }
  return {
    id: typeof raw.id === "string" ? raw.id : null,
    name: typeof raw.name === "string" ? raw.name : null,
    current_hp: currentHp,
    max_hp: coerceNumber(raw.max_hp),
    intent: typeof raw.intent === "string" ? raw.intent : null,
    intent_damage: firstNumber(raw, ["intent_damage", "move_base_damage", "base_damage", "damage"]),
    intent_hits: firstNumber(raw, ["intent_hits", "intent_multi_amt", "move_hits", "multiplier"]),
    block: coerceNumber(raw.block),
  };
}

function firstNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = coerceNumber(record[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function coerceNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function findFirstArray(value: unknown, keys: string[], depth = 6): unknown[] {
  if (depth < 0 || !value) {
    return [];
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findFirstArray(item, keys, depth - 1);
      if (found.length) {
        return found;
      }
    }
    return [];
  }
  if (typeof value !== "object") {
    return [];
  }
  const record = value as Record<string, unknown>;
  for (const [key, nested] of Object.entries(record)) {
    if (keys.includes(key) && Array.isArray(nested)) {
      return nested;
    }
    const found = findFirstArray(nested, keys, depth - 1);
    if (found.length) {
      return found;
    }
  }
  return [];
}

function findFirstNumber(value: unknown, keys: string[], depth = 6): number | null {
  if (depth < 0 || !value) {
    return null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findFirstNumber(item, keys, depth - 1);
      if (found !== null) {
        return found;
      }
    }
    return null;
  }
  if (typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  for (const [key, nested] of Object.entries(record)) {
    if (keys.includes(key)) {
      const number = coerceNumber(nested);
      if (number !== null) {
        return number;
      }
    }
    const found = findFirstNumber(nested, keys, depth - 1);
    if (found !== null) {
      return found;
    }
  }
  return null;
}

onMounted(startPolling);
onBeforeUnmount(stopPolling);
</script>

<template>
  <main class="dashboard">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Slay The Spire</p>
        <h1>智能顾问</h1>
        <p class="subtitle">
          实时接收 Communication Mod 状态，统一展示局面分析、聊天答复和最近一次自动建议。
        </p>
      </div>

      <aside class="status-card">
        <div class="status-badge">
          <span class="status-dot" :class="{ live: !fetchError && latestState, disconnected: !!fetchError }"></span>
          <div>
            <strong>{{ connectionLabel }}</strong>
            <p>{{ statusSummary }}</p>
          </div>
        </div>

        <div class="status-meta">
          <p>API：{{ API_BASE }}</p>
          <p>最近刷新：{{ lastFetchAt ?? "--" }}</p>
          <p>会话：{{ assistantState?.session_id ?? "--" }}</p>
        </div>

        <div class="status-actions">
          <button type="button" class="ghost-button" @click="refreshState">刷新状态</button>
          <button type="button" class="primary-button" :disabled="analyzeLoading" @click="analyzeCurrentState">
            {{ analyzeLoading ? "分析中..." : "一键分析当前局面" }}
          </button>
        </div>
      </aside>
    </section>

    <section v-if="fetchError" class="banner error-banner">
      <strong>连接错误</strong>
      <p>{{ fetchError }}</p>
    </section>

    <section v-if="submitError" class="banner warning-banner">
      <strong>请求失败</strong>
      <p>{{ submitError }}</p>
    </section>

    <section v-if="loading" class="empty-panel">
      <h2>正在等待后端状态</h2>
      <p>助手会在收到游戏状态后自动补齐界面内容。</p>
    </section>

    <template v-else>
      <section class="onboarding-panel">
        <div class="panel-header compact">
          <div>
            <p class="panel-kicker">上手与诊断</p>
            <h2>{{ quickGuideTitle }}</h2>
          </div>
          <span class="panel-stamp">{{ diagnostics?.recommendation_source ?? "未分析" }}</span>
        </div>
        <div class="diagnostic-grid">
          <div class="diagnostic-item">
            <span>后端</span>
            <strong>{{ fetchError ? "未连上" : "已连接" }}</strong>
          </div>
          <div class="diagnostic-item">
            <span>模型</span>
            <strong>{{ diagnostics?.llm_configured ? "已配置" : "未配置" }}</strong>
          </div>
          <div class="diagnostic-item">
            <span>最近界面</span>
            <strong>{{ diagnostics?.last_screen_type ? screenLabel(diagnostics.last_screen_type) : "--" }}</strong>
          </div>
          <div class="diagnostic-item">
            <span>战斗详情</span>
            <strong>{{ diagnostics?.has_combat_data ? "已收到" : "未收到" }}</strong>
          </div>
        </div>
        <div class="guide-card">
          <h3>下一步</h3>
          <p class="guide-lead">{{ diagnostics?.next_step ?? "先让游戏推送一份状态到本地 API。" }}</p>
          <ol class="guide-list">
            <li v-for="step in quickGuideSteps" :key="step">{{ step }}</li>
          </ol>
        </div>
      </section>

      <section class="stats-grid">
        <article class="stat-card">
          <span>角色</span>
          <strong>{{ characterLabel(latestState?.character_class ?? null) }}</strong>
        </article>
        <article class="stat-card">
          <span>进阶 / 楼层</span>
          <strong>A{{ valueOrQuestion(latestState?.ascension_level ?? null) }} / F{{ valueOrQuestion(latestState?.floor ?? null) }}</strong>
        </article>
        <article class="stat-card">
          <span>生命</span>
          <strong>{{ valueOrQuestion(latestState?.current_hp ?? null) }} / {{ valueOrQuestion(latestState?.max_hp ?? null) }}</strong>
        </article>
        <article class="stat-card">
          <span>金币 / 卡组</span>
          <strong>{{ valueOrQuestion(latestState?.gold ?? null) }} / {{ latestState?.deck_size ?? 0 }}</strong>
        </article>
      </section>

      <section class="main-grid">
        <article class="assistant-panel">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">{{ latestAnalysisTitle }}</p>
              <h2>顾问主面板</h2>
            </div>
            <span class="panel-stamp">{{ formatTimestamp(activeReply?.created_at ?? assistantState?.updated_at) }}</span>
          </div>


          <template v-if="activeReply">
            <section class="reply-card">
              <div class="reply-header">
                <h3>现在就点</h3>
                <span class="reply-tag">{{ recommendationActionLabel }}</span>
              </div>
              <div class="decision-hero">
                <p class="decision-label">主推荐</p>
                <strong>{{ recommendationActionLabel }}<template v-if="recommendationTargetLabel !== '--'"> · {{ recommendationTargetLabel }}</template></strong>
                <p class="decision-subtitle">{{ activeReply.conclusion }}</p>
              </div>
              <div class="summary-grid">
                <div class="summary-item">
                  <span>推荐操作</span>
                  <strong>{{ recommendationActionLabel }}</strong>
                </div>
                <div class="summary-item">
                  <span>推荐目标</span>
                  <strong>{{ recommendationTargetLabel }}</strong>
                </div>
                <div class="summary-item">
                  <span>构筑方向</span>
                  <strong>{{ recommendationBuildDirection ?? "待补充" }}</strong>
                </div>
                <div class="summary-item">
                  <span>契合当前构筑</span>
                  <strong>{{ recommendationFitLabel }}</strong>
                </div>
                <div class="summary-item">
                  <span>拿了后会走</span>
                  <strong>{{ recommendationRouteAfterPick }}</strong>
                </div>
                <div class="summary-item">
                  <span>把握度</span>
                  <strong>{{ recommendationConfidenceLabel }}</strong>
                </div>
              </div>
              <section class="callout-card">
                <span>不这么做的代价</span>
                <strong>{{ recommendationOpportunityCost }}</strong>
              </section>
            </section>

            <section class="reply-card">
              <h3>原因</h3>
              <ul class="reason-list">
                <li v-for="reason in activeReply.reasons.slice(0, 3)" :key="reason">{{ reason }}</li>
              </ul>
            </section>

            <section class="reply-card coach-grid-card">
              <div class="coach-grid">
                <section class="coach-note-card">
                  <span>这次学到的判断规则</span>
                  <strong>{{ recommendationLearningRule }}</strong>
                </section>
                <section class="coach-note-card">
                  <span>这张牌在补什么</span>
                  <strong>{{ recommendationFillsGap }}</strong>
                </section>
                <section class="coach-note-card">
                  <span>拿不准时先怎么选</span>
                  <strong>{{ recommendationSafeDefault }}</strong>
                </section>
              </div>
            </section>

          <section class="player-mode-panel inline-guide-panel">
            <div class="player-mode-header">
              <div>
                <p class="panel-kicker">辅助理解</p>
                <h3>这条建议怎么看</h3>
              </div>
            </div>
            <p class="player-mode-lead">{{ guideLead }}</p>
            <ul class="mode-note-list">
              <li v-for="note in guideNotes" :key="note">{{ note }}</li>
            </ul>
          </section>



            <section class="reply-card">
              <h3>备选</h3>
              <div v-if="displayAlternatives.length" class="tag-row">
                <span v-for="item in displayAlternatives" :key="item" class="tag">{{ item }}</span>
              </div>
              <p v-else class="muted-text">当前没有额外备选项。</p>
            </section>
          </template>
          <template v-else>
            <section class="reply-card">
              <h3>结论</h3>

              <p class="muted-text">还没有分析结果，进入一局游戏后点“一键分析当前局面”。</p>
            </section>
          </template>

          <section class="chat-section">
            <div class="panel-header compact">
              <div>
                <p class="panel-kicker">局内记忆</p>
                <h3>聊天历史</h3>
              </div>
              <span class="panel-stamp">{{ assistantState?.memory_enabled ? "已开启" : "未开启" }}</span>
            </div>

            <div class="chat-list">
              <article v-for="item in chatHistory" :key="`${item.created_at}-${item.question}`" class="chat-item">
                <p class="chat-question">你问：{{ item.question }}</p>
                <p class="chat-answer">助手：{{ item.reply.conclusion }}</p>
                <ul v-if="item.reply.reasons?.length" class="chat-reason-list">
                  <li v-for="reason in item.reply.reasons.slice(0, 3)" :key="`${item.created_at}-${reason}`">
                    {{ reason }}
                  </li>
                </ul>
                <p class="chat-time">{{ formatTimestamp(item.created_at) }}</p>
              </article>
              <div v-if="!chatHistory.length" class="chat-empty">
                这里会保留本局最近 8 轮问答。
              </div>
            </div>

            <div class="template-row">
              <button
                v-for="template in beginnerQuestionTemplates"
                :key="template"
                type="button"
                class="template-chip"
                @click="useQuestionTemplate(template)"
              >
                {{ template }}
              </button>
            </div>

            <div class="chat-compose">
              <textarea
                v-model="chatInput"
                rows="3"
                :placeholder="chatPlaceholder"
                @keydown.enter.exact.prevent="handleSendChat"
              />
              <button type="button" class="primary-button" :disabled="!canSendChat" @click="handleSendChat">
                {{ chatLoading ? "发送中..." : "发送问题" }}
              </button>
            </div>
          </section>
        </article>

        <article class="context-panel">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">当前界面</p>
              <h2>{{ currentScreenLabel }}</h2>
            </div>
            <span class="panel-stamp">{{ latestState?.ready_for_command ? "可交互" : "等待中" }}</span>
          </div>

          <template v-if="normalizedScreen?.card_reward">
            <div class="flag-row">
              <span class="tag">可跳过：{{ normalizedScreen.card_reward.skip_available ? "是" : "否" }}</span>
              <span class="tag">可拿汤：{{ normalizedScreen.card_reward.bowl_available ? "是" : "否" }}</span>
            </div>
            <div class="candidate-list">
              <article
                v-for="card in normalizedScreen.card_reward.cards"
                :key="`${card.id}-${card.choice_index}`"
                class="candidate-card"
                :class="{ highlight: cardMatchesTarget(card) }"
              >
                <div class="candidate-top">
                  <strong>{{ safeCardDisplayName(card) }}</strong>
                  <span>#{{ card.choice_index }}</span>
                </div>
                <p>{{ cardTypeLabel(card.type) }} / {{ cardRarityLabel(card.rarity) }}</p>
                <p>费用：{{ card.cost ?? "?" }}</p>
              </article>
            </div>
          </template>

          <template v-else-if="normalizedScreen?.shop">
            <section class="shop-block">
              <div class="shop-header">
                <h3>商店卡牌</h3>
                <span class="tag">删牌：{{ normalizedScreen.shop.purge_available ? normalizedScreen.shop.purge_cost ?? "?" : "不可用" }}</span>
              </div>
              <div class="candidate-list">
                <article
                  v-for="card in normalizedScreen.shop.cards"
                  :key="`${card.id}-${card.choice_index}`"
                  class="candidate-card"
                  :class="{ highlight: cardMatchesTarget(card) }"
                >
                  <div class="candidate-top">
                    <strong>{{ safeCardDisplayName(card) }}</strong>
                    <span>{{ card.price ?? "?" }}g</span>
                  </div>
                  <p>{{ cardTypeLabel(card.type) }} / {{ cardRarityLabel(card.rarity) }}</p>
                  <p>费用：{{ card.cost ?? "?" }}</p>
                </article>
              </div>
            </section>

            <section class="shop-block">
              <h3>遗物</h3>
              <div class="candidate-list compact-list">
                <article
                  v-for="relic in normalizedScreen.shop.relics"
                  :key="`${relic.id}-${relic.choice_index}`"
                  class="candidate-card"
                  :class="{ highlight: relicMatchesTarget(relic) }"
                >
                  <div class="candidate-top">
                    <strong>{{ safeRelicDisplayName(relic) }}</strong>
                    <span>{{ relic.price ?? "?" }}g</span>
                  </div>
                </article>
              </div>
            </section>

            <section class="shop-block">
              <h3>药水</h3>
              <div class="candidate-list compact-list">
                <article
                  v-for="potion in normalizedScreen.shop.potions"
                  :key="`${potion.id}-${potion.choice_index}`"
                  class="candidate-card"
                  :class="{ highlight: potionMatchesTarget(potion) }"
                >
                  <div class="candidate-top">
                    <strong>{{ safePotionDisplayName(potion) }}</strong>
                    <span>{{ potion.price ?? "?" }}g</span>
                  </div>
                </article>
              </div>
            </section>
          </template>

          <template v-else-if="normalizedScreen?.relic_reward">
            <section class="shop-block">
              <div class="shop-header">
                <h3>遗物选择</h3>
                <span class="tag">{{ normalizedScreen.relic_reward.source ?? currentScreenLabel }}</span>
              </div>
              <div v-if="normalizedScreen.relic_reward.sapphire_key_available" class="flag-row">
                <span class="tag" :class="{ highlight: recommendationTargetLabel === '蓝钥匙' }">
                  蓝钥匙
                  <template v-if="normalizedScreen.relic_reward.linked_relic">
                    / 放弃 {{ safeRelicDisplayName(normalizedScreen.relic_reward.linked_relic) }}
                  </template>
                </span>
              </div>
              <div class="candidate-list compact-list">
                <article
                  v-for="relic in normalizedScreen.relic_reward.relics"
                  :key="`${relic.id}-${relic.choice_index}`"
                  class="candidate-card"
                  :class="{ highlight: relicMatchesTarget(relic) }"
                >
                  <div class="candidate-top">
                    <strong>{{ safeRelicDisplayName(relic) }}</strong>
                    <span v-if="relic.choice_index !== null">#{{ relic.choice_index }}</span>
                  </div>
                </article>
              </div>
            </section>
          </template>

          <template v-else-if="!hasCombatContext">
            <div class="empty-card">
              <p>当前不在奖励或商店界面，助手仍然可以用于地图、事件和战斗阶段分析。</p>
            </div>
          </template>

          <section v-if="hasCombatContext" class="combat-panel">
            <div class="panel-header compact">
              <div>
                <p class="panel-kicker">战斗状态</p>
                <h3>回合作战单</h3>
              </div>
              <span class="panel-stamp">能量 {{ combatEnergy ?? "?" }}</span>
            </div>

            <section class="reply-card coach-grid-card combat-plan-card">
              <div class="coach-grid combat-plan-grid">
                <section class="coach-note-card">
                  <span>先做什么</span>
                  <strong>{{ combatStepOne }}</strong>
                </section>
                <section class="coach-note-card">
                  <span>再做什么</span>
                  <strong>{{ combatStepTwo }}</strong>
                </section>
                <section class="coach-note-card">
                  <span>什么时候交药</span>
                  <strong>{{ combatStepThree }}</strong>
                </section>
              </div>
            </section>

            <div class="summary-grid combat-brief-grid">
              <div class="summary-item">
                <span>推荐起手</span>
                <strong>{{ recommendationTargetLabel }}</strong>
              </div>
              <div class="summary-item">
                <span>建议顺序</span>
                <strong>{{ combatSequence.length ? combatSequence.join(" -> ") : "先减伤再补输出" }}</strong>
              </div>
              <div class="summary-item">
                <span>本回合至少要挡多少</span>
                <strong>{{ combatBlockThreshold ?? combatIncomingDamage ?? "?" }}</strong>
              </div>
              <div class="summary-item">
                <span>药水提醒</span>
                <strong>{{ combatPotionHint }}</strong>
              </div>
            </div>

            <div class="combat-grid">
              <section class="combat-block">
                <div class="combat-block-header">
                  <h4>手牌</h4>
                  <span>{{ combatHand.length }} 张</span>
                </div>
                <div v-if="combatHand.length" class="candidate-list compact-list">
                  <article v-for="card in combatHand" :key="`${card.id}-${card.name}`" class="candidate-card">
                    <div class="candidate-top">
                      <strong>{{ safeCombatCardDisplayName(card) }}</strong>
                      <span>{{ card.cost ?? "?" }}费</span>
                    </div>
                    <p>{{ cardTypeLabel(card.type) }} / {{ card.is_playable === false ? "暂不可打" : "可考虑出" }}</p>
                  </article>
                </div>
                <p v-else class="muted-text">当前状态里还没收到手牌信息。</p>
              </section>

              <section class="combat-block">
                <div class="combat-block-header">
                  <h4>敌人意图</h4>
                  <span>预计伤害 {{ combatIncomingDamage ?? "?" }}</span>
                </div>
                <div v-if="combatMonsters.length" class="candidate-list">
                  <article v-for="(monster, index) in combatMonsters" :key="`${monster.id ?? monster.name ?? 'monster'}-${index}`" class="candidate-card">
                    <div class="candidate-top">
                      <strong>{{ monster.name ?? `敌人 ${index + 1}` }}</strong>
                      <span>{{ monster.current_hp ?? "?" }} / {{ monster.max_hp ?? "?" }}</span>
                    </div>
                    <p>意图：{{ monster.intent ?? "未知" }}</p>
                    <p>伤害：{{ monster.intent_damage ?? 0 }}<template v-if="(monster.intent_hits ?? 1) > 1"> x {{ monster.intent_hits }}</template></p>
                  </article>
                </div>
                <p v-else class="muted-text">当前状态里还没收到敌人和意图详情。</p>
              </section>
            </div>
          </section>

          <section class="deck-panel">
            <div class="panel-header compact">
              <div>
                <p class="panel-kicker">构筑方案</p>
                <h3>{{ buildProfile?.name ?? "当前构筑分析" }}</h3>
              </div>
              <span class="panel-stamp">评级 {{ buildProfile?.rating ?? "--" }}</span>
            </div>
            <div v-if="buildProfile" class="build-profile">
              <p class="build-summary">{{ buildProfile.summary }}</p>
              <div class="summary-grid build-grid">
                <div class="summary-item">
                  <span>这局现在先学什么</span>
                  <strong>{{ buildProfile.route_stage ?? "先把当前局面稳住" }}</strong>
                </div>
                <div class="summary-item">
                  <span>接下来两场重点找什么</span>
                  <strong>{{ buildProfile.two_fight_goal?.length ? buildProfile.two_fight_goal.join(" / ") : "优先补当前短板" }}</strong>
                </div>
                <div class="summary-item">
                  <span>现在先别拿什么</span>
                  <strong>{{ buildProfile.avoid_now?.length ? buildProfile.avoid_now.join(" / ") : "少拿无关散件" }}</strong>
                </div>
                <div class="summary-item">
                  <span>什么时候再换路线</span>
                  <strong>{{ buildProfile.pivot_triggers?.length ? buildProfile.pivot_triggers.join(" / ") : "摸到明显核心再锁线" }}</strong>
                </div>
              </div>
              <section class="build-section">
                <h4>社区判断</h4>
                <p class="muted-text">{{ buildProfile.tier_label ?? "暂未给出路线强度标签" }}</p>
                <p v-if="buildProfile.community_summary" class="muted-text build-community-summary">{{ buildProfile.community_summary }}</p>
              </section>
              <div v-if="buildProfile.source_tags?.length" class="tag-row build-source-tags">
                <span v-for="tag in buildProfile.source_tags" :key="`build-source-${tag}`" class="tag">{{ tag }}</span>
              </div>
              <div class="summary-grid build-grid">
                <div class="summary-item">
                  <span>核心牌</span>
                  <strong>{{ buildProfile.core_cards.length ? buildProfile.core_cards.join(" / ") : "还在成型中" }}</strong>
                </div>
                <div class="summary-item">
                  <span>辅助牌</span>
                  <strong>{{ buildProfile.support_cards.length ? buildProfile.support_cards.join(" / ") : "待补充" }}</strong>
                </div>
                <div class="summary-item">
                  <span>接下来继续补什么</span>
                  <strong>{{ buildProfile.next_picks.length ? buildProfile.next_picks.join(" / ") : "优先补当前短板" }}</strong>
                </div>
                <div class="summary-item">
                  <span>和你现在这套牌合不合</span>
                  <strong>{{ recommendationFitLabel }}</strong>
                </div>
              </div>
              <div class="build-columns">
                <section class="build-section">
                  <h4>这套构筑为什么强</h4>
                  <ul class="reason-list">
                    <li v-for="item in buildProfile.strengths" :key="`strength-${item}`">{{ item }}</li>
                  </ul>
                </section>
                <section class="build-section">
                  <h4>这套构筑现在最怕什么</h4>
                  <ul class="reason-list">
                    <li v-for="item in buildProfile.risks" :key="`risk-${item}`">{{ item }}</li>
                  </ul>
                </section>
              </div>
              <section v-if="buildProfile.missing_pieces.length" class="build-section">
                <h4>当前还缺什么</h4>
                <div class="tag-row">
                  <span v-for="item in buildProfile.missing_pieces" :key="`missing-${item}`" class="tag">{{ item }}</span>
                </div>
              </section>
              <section v-if="buildCommunitySources.length" class="build-section">
                <h4>社区来源</h4>
                <div class="build-source-list">
                  <article
                    v-for="source in buildCommunitySources"
                    :key="`${source.source_id ?? source.url}`"
                    class="build-source-card"
                  >
                    <div class="candidate-top">
                      <strong>{{ source.title }}</strong>
                      <span>{{ communityStatusLabel(source.raw_status) }}</span>
                    </div>
                    <p class="muted-text">{{ source.publisher }} · {{ source.published_at || "unknown" }}</p>
                    <p class="muted-text">{{ source.summary }}</p>
                    <p v-if="source.excerpt" class="muted-text build-source-excerpt">{{ source.excerpt }}</p>
                  </article>
                </div>
              </section>
              <section v-if="buildAlternatives.length" class="build-section">
                <h4>可转型路线</h4>
                <div class="build-option-list">
                  <article v-for="option in buildAlternatives" :key="option.key" class="build-option-card">
                    <div class="candidate-top">
                      <strong>{{ option.name }}</strong>
                      <span>{{ option.rating }} / {{ Math.round(option.score * 100) }}分</span>
                    </div>
                    <p class="muted-text">{{ option.summary }}</p>
                    <p v-if="option.tier_label" class="muted-text">{{ option.tier_label }}</p>
                    <p v-if="option.community_summary" class="muted-text build-community-summary">{{ option.community_summary }}</p>
                    <div v-if="option.source_tags?.length" class="tag-row build-source-tags compact-tags">
                      <span v-for="tag in option.source_tags" :key="`${option.key}-${tag}`" class="tag">{{ tag }}</span>
                    </div>
                    <p class="muted-text">为什么可走：{{ option.pivot_reason }}</p>
                    <p class="muted-text">核心牌：{{ option.core_cards.length ? option.core_cards.join(" / ") : "当前还没摸到明显核心" }}</p>
                    <p class="muted-text">风险提示：{{ option.risks.length ? option.risks[0] : "先观察后续奖励再决定是否深走" }}</p>
                    <p class="muted-text">下一步：{{ option.next_picks.length ? option.next_picks.join(" / ") : "先补关键组件" }}</p>
                  </article>
                </div>
              </section>
            </div>
            <div v-else class="empty-card">
              <p>还没有足够信息来判断当前构筑方向，先继续推进当前对局。</p>
            </div>
          </section>

          <section class="deck-panel">
            <div class="panel-header compact">
              <div>
                <p class="panel-kicker">牌组摘要</p>
                <h3>当前套牌</h3>
              </div>
              <span class="panel-stamp">{{ latestState?.deck_size ?? 0 }} 张</span>
            </div>
            <div class="deck-list">
              <div
                v-for="card in latestState?.deck_breakdown ?? []"
                :key="`${card.id}-${card.upgrades}`"
                class="deck-row"
              >
                <strong>{{ safeDeckCardDisplayName(card) }}</strong>
                <span>x{{ card.copies }}</span>
              </div>
            </div>
          </section>

          <section class="relic-panel">
            <div class="panel-header compact">
              <div>
                <p class="panel-kicker">遗物</p>
                <h3>当前持有</h3>
              </div>
              <span class="panel-stamp">{{ latestState?.relics.length ?? 0 }}</span>
            </div>
            <div class="tag-row">
              <span v-for="relic in latestState?.relics ?? []" :key="relic.id" class="tag">{{ safeRelicDisplayName(relic) }}</span>
            </div>
          </section>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.dashboard {
  max-width: 1480px;
  margin: 0 auto;
  padding: 28px 22px 42px;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr);
  gap: 18px;
  margin-bottom: 18px;
}

.hero-copy,
.status-card,
.stat-card,
.assistant-panel,
.context-panel,
.onboarding-panel,
.banner,
.empty-panel {
  border: 1px solid rgba(98, 53, 19, 0.18);
  border-radius: 28px;
  background: linear-gradient(180deg, rgba(255, 247, 230, 0.95), rgba(244, 229, 202, 0.92));
  box-shadow: 0 20px 50px rgba(75, 42, 13, 0.12);
}

.hero-copy {
  padding: 28px;
  min-height: 190px;
  background:
    radial-gradient(circle at right top, rgba(189, 105, 28, 0.2), transparent 34%),
    linear-gradient(135deg, rgba(78, 39, 12, 0.92), rgba(132, 79, 26, 0.84));
  color: #fff6eb;
}

.eyebrow,
.panel-kicker {
  margin: 0 0 10px;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero-copy .eyebrow {
  color: rgba(255, 222, 177, 0.82);
}

h1 {
  margin: 0;
  font-size: clamp(2.4rem, 4vw, 4.6rem);
  line-height: 0.94;
}

.subtitle {
  max-width: 720px;
  margin: 16px 0 0;
  color: rgba(255, 241, 218, 0.88);
  font-size: 1.02rem;
}

.status-card {
  padding: 22px;
  display: grid;
  gap: 18px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 14px;
}

.status-badge strong {
  display: block;
  margin-bottom: 4px;
  color: #42250b;
}

.status-badge p,
.status-meta p {
  margin: 0;
  color: #6d4c28;
}

.status-meta {
  display: grid;
  gap: 6px;
}

.status-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  background: #d08f29;
  box-shadow: 0 0 0 8px rgba(208, 143, 41, 0.18);
}

.status-dot.live {
  background: #297c49;
  box-shadow: 0 0 0 8px rgba(41, 124, 73, 0.18);
}

.status-dot.disconnected {
  background: #b04636;
  box-shadow: 0 0 0 8px rgba(176, 70, 54, 0.18);
}

.status-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-button,
.ghost-button {
  border: none;
  border-radius: 999px;
  padding: 11px 16px;
  cursor: pointer;
  transition: transform 120ms ease, opacity 120ms ease;
}

.primary-button {
  background: linear-gradient(135deg, #a14f1d, #d48634);
  color: #fff9f0;
}

.ghost-button {
  background: rgba(102, 58, 24, 0.08);
  color: #5f3a16;
}

.primary-button:disabled,
.ghost-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.primary-button:hover:not(:disabled),
.ghost-button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.banner,
.empty-panel {
  padding: 18px 20px;
  margin-bottom: 18px;
}

.banner strong,
.empty-panel h2 {
  color: #43240b;
}

.banner p,
.empty-panel p {
  margin: 8px 0 0;
  color: #6e4b28;
}

.error-banner {
  background: linear-gradient(180deg, rgba(255, 238, 232, 0.96), rgba(246, 218, 210, 0.92));
}

.warning-banner {
  background: linear-gradient(180deg, rgba(255, 245, 224, 0.96), rgba(247, 229, 197, 0.92));
}

.stats-grid,
.main-grid {
  display: grid;
  gap: 18px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 18px;
}

.stat-card {
  padding: 18px 20px;
}

.stat-card span {
  color: #79552d;
}

.stat-card strong {
  display: block;
  margin-top: 8px;
  font-size: 1.36rem;
  color: #371f09;
}

.main-grid {
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
}

.assistant-panel,
.context-panel {
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.panel-header.compact {
  margin-bottom: 12px;
}

.panel-header h2,
.panel-header h3 {
  margin: 0;
  color: #311a07;
}

.panel-stamp {
  border-radius: 999px;
  padding: 6px 12px;
  background: rgba(121, 84, 38, 0.1);
  color: #6f4821;
  font-size: 0.9rem;
  white-space: nowrap;
}

.reply-card,
.chat-section,
.deck-panel,
.relic-panel,
.shop-block,
.empty-card {
  border-radius: 22px;
  border: 1px solid rgba(109, 69, 28, 0.12);
  background: rgba(255, 255, 255, 0.56);
  padding: 16px;
}

.build-profile {
  display: grid;
  gap: 14px;
}

.build-summary {
  margin: 0;
  color: #43250d;
  line-height: 1.7;
}

.build-grid {
  margin-bottom: 0;
}

.build-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.build-option-list {
  display: grid;
  gap: 10px;
}

.build-option-card {
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.build-community-summary {
  line-height: 1.7;
}

.build-source-list,
.build-option-source-list {
  display: grid;
  gap: 10px;
}

.build-source-card {
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.build-source-excerpt {
  margin-top: 6px;
  color: #7a5934;
  line-height: 1.6;
}

.build-section {
  border-radius: 18px;
  padding: 12px 14px;
  background: rgba(250, 245, 235, 0.92);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.build-section h4 {
  margin: 0 0 8px;
  color: #3b2109;
}

.reply-card + .reply-card,
.reply-card + .chat-section,
.shop-block + .shop-block,
.deck-panel + .relic-panel {
  margin-top: 14px;
}

.reply-card h3,
.shop-block h3 {
  margin: 0 0 10px;
  color: #3b2109;
}

.reply-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.reply-conclusion {
  margin: 0;
  font-size: 1.08rem;
  line-height: 1.7;
  color: #2f1704;
}

.decision-hero,
.callout-card {
  border-radius: 18px;
  padding: 14px 16px;
  margin-bottom: 14px;
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.decision-hero {
  background: linear-gradient(180deg, rgba(255, 249, 238, 0.98), rgba(243, 228, 199, 0.92));
}

.decision-label,
.callout-card span {
  margin: 0;
  display: block;
  color: #7a5934;
  font-size: 0.86rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.decision-hero strong,
.callout-card strong {
  display: block;
  margin-top: 8px;
  color: #2f1704;
  line-height: 1.55;
}

.decision-hero strong {
  font-size: 1.34rem;
}

.decision-subtitle {
  margin: 8px 0 0;
  color: #5d4020;
  line-height: 1.65;
}

.callout-card {
  background: rgba(250, 245, 235, 0.92);
}

.summary-grid,
.combat-grid {
  display: grid;
  gap: 10px;
}

.summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  margin-bottom: 14px;
}

.combat-brief-grid {
  margin-bottom: 14px;
}

.summary-item,
.diagnostic-item,
.combat-block {
  border-radius: 18px;
  padding: 12px 14px;
  background: rgba(250, 245, 235, 0.92);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.summary-item span,
.combat-block-header span {
  display: block;
  color: #7a5934;
  font-size: 0.88rem;
}

.summary-item strong {
  display: block;
  margin-top: 6px;
  color: #2f1905;
  line-height: 1.5;
}

.player-mode-panel {
  margin-bottom: 16px;
  border-radius: 22px;
  padding: 16px 18px;
  background: linear-gradient(180deg, rgba(255, 250, 239, 0.92), rgba(246, 236, 215, 0.88));
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.inline-guide-panel {
  margin-top: 14px;
  margin-bottom: 0;
}

.player-mode-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.player-mode-header h3 {
  margin: 0;
  color: #341d08;
}

.player-mode-lead {
  margin: 12px 0 10px;
  color: #50371c;
  line-height: 1.65;
}

.mode-note-list {
  margin: 0;
  padding-left: 20px;
  color: #5e4321;
}

.coach-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
}

.coach-note-card {
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(250, 245, 235, 0.92);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.coach-note-card span {
  display: block;
  color: #7a5934;
  font-size: 0.84rem;
  margin-bottom: 6px;
}

.coach-note-card strong {
  color: #2f1905;
  line-height: 1.6;
}

.template-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.template-chip {
  border: 1px solid rgba(112, 75, 31, 0.14);
  background: rgba(250, 245, 235, 0.92);
  color: #5f3a16;
  border-radius: 999px;
  padding: 8px 12px;
  cursor: pointer;
}

.template-chip:hover {
  transform: translateY(-1px);
}

.onboarding-panel {
  padding: 18px 20px;
  margin-bottom: 18px;
}

.diagnostic-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.diagnostic-item span {
  display: block;
  color: #7a5934;
  font-size: 0.88rem;
}

.diagnostic-item strong {
  display: block;
  margin-top: 6px;
  color: #2f1905;
  line-height: 1.5;
}

.guide-card {
  margin-top: 14px;
  border-radius: 18px;
  padding: 14px 16px;
  background: rgba(255, 252, 244, 0.88);
  border: 1px solid rgba(112, 75, 31, 0.12);
}

.guide-card h3 {
  margin: 0 0 8px;
  color: #3b2109;
}

.guide-lead {
  margin: 0 0 10px;
  color: #5f4322;
}

.guide-list {
  margin: 0;
  padding-left: 20px;
  color: #5a4123;
}

.combat-panel {
  border-radius: 22px;
  border: 1px solid rgba(109, 69, 28, 0.12);
  background: rgba(255, 255, 255, 0.56);
  padding: 16px;
  margin-top: 14px;
}

.combat-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.combat-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.combat-block h4 {
  margin: 0;
  color: #3b2109;
}

.reply-tag,
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 5px 10px;
  background: rgba(121, 84, 38, 0.09);
  color: #6b451e;
}

.reason-list {
  margin: 0;
  padding-left: 20px;
  color: #51341b;
  display: grid;
  gap: 8px;
}

.muted-text {
  margin: 0;
  color: #7b5a34;
}

.chat-list {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
  max-height: 300px;
  overflow: auto;
  padding-right: 4px;
}

.chat-item {
  border-radius: 18px;
  padding: 12px 14px;
  background: rgba(246, 239, 225, 0.88);
  border: 1px solid rgba(115, 74, 28, 0.1);
}

.chat-question,
.chat-answer,
.chat-time,
.candidate-card p,
.empty-card p {
  margin: 0;
}

.chat-question {
  color: #6a3f18;
}

.chat-answer {
  margin-top: 6px;
  color: #35200c;
}

.chat-reason-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #5b4020;
  display: grid;
  gap: 6px;
}

.chat-time {
  margin-top: 8px;
  color: #8a6940;
  font-size: 0.86rem;
}

.chat-empty {
  border-radius: 18px;
  padding: 16px;
  color: #7a5934;
  background: rgba(246, 239, 225, 0.7);
}

.chat-compose {
  display: grid;
  gap: 10px;
}

.chat-compose textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid rgba(110, 75, 32, 0.2);
  border-radius: 18px;
  padding: 12px 14px;
  background: rgba(255, 252, 247, 0.9);
  color: #301905;
}

.flag-row,
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.flag-row {
  margin-bottom: 12px;
}

.candidate-list,
.deck-list {
  display: grid;
  gap: 10px;
}

.compact-list {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.candidate-card,
.deck-row {
  border-radius: 18px;
  padding: 12px 14px;
  border: 1px solid rgba(112, 75, 31, 0.12);
  background: rgba(255, 255, 255, 0.72);
}

.candidate-card.highlight {
  border-color: rgba(49, 127, 77, 0.36);
  background: rgba(227, 246, 234, 0.92);
}

.candidate-top,
.deck-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.candidate-card strong,
.deck-row strong {
  color: #2f1905;
}

.candidate-card p {
  margin-top: 6px;
  color: #6a4a28;
}

.shop-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.build-source-tags {
  margin: 12px 0 0;
}

.compact-tags {
  margin: 10px 0;
}

@media (max-width: 1180px) {
  .hero,
  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .dashboard {
    padding: 16px 14px 28px;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .status-actions {
    flex-direction: column;
  }

  .reply-header,
  .shop-header,
  .panel-header {
    flex-direction: column;
  }

  .summary-grid,
  .diagnostic-grid,
  .combat-grid,
  .build-columns {
    grid-template-columns: 1fr;
  }

  .player-mode-header {
    flex-direction: column;
  }
}
</style>
