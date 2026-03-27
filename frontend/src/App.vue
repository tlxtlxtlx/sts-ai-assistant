<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

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

interface ScreenNormalized {
  screen_type: string;
  card_reward?: CardRewardView;
  shop?: ShopView;
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
  screen: {
    screen_type: string;
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
}

interface AssistantReply {
  mode: "analysis" | "chat";
  conclusion: string;
  reasons: string[];
  alternatives: string[];
  build_direction: string | null;
  source: "auto" | "web" | "ingame";
  created_at: string;
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

interface ApiState {
  updated_at: string | null;
  latest_state: LatestState | null;
  latest_recommendation: Recommendation | null;
  assistant: AssistantState;
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
const assistantState = computed<AssistantState | null>(() => apiState.value?.assistant ?? null);
const latestAnalysis = computed<AssistantReply | null>(() => assistantState.value?.latest_analysis ?? null);
const normalizedScreen = computed(() => latestState.value?.screen.normalized ?? null);
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
const currentTarget = computed(() => latestRecommendation.value?.primary_target ?? null);
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
const activeReply = computed<AssistantReply | null>(() => latestAnalysis.value ?? fallbackAnalysis.value);
const chatHistory = computed(() => assistantState.value?.chat_history ?? []);
const statusSummary = computed(() => {
  if (!latestState.value) {
    return "等待游戏状态";
  }
  return `${characterLabel(latestState.value.character_class)} A${valueOrQuestion(latestState.value.ascension_level)} · ${currentScreenLabel.value}`;
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

async function sendChat() {
  const message = chatInput.value.trim();
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
    COMBAT_REWARD: "战斗奖励",
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
  const target = recommendation.primary_target;
  if (action === "TAKE") {
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
  return target ? `建议优先考虑${target}。` : "建议先走保守线。";
}

function cardMatchesTarget(card: CardView): boolean {
  const target = currentTarget.value;
  if (!target) {
    return false;
  }
  return [card.display_name, card.name, card.id].includes(target);
}

function relicMatchesTarget(relic: RelicView): boolean {
  const target = currentTarget.value;
  if (!target) {
    return false;
  }
  return [relic.name, relic.id].includes(target);
}

function potionMatchesTarget(potion: PotionView): boolean {
  const target = currentTarget.value;
  if (!target) {
    return false;
  }
  return [potion.name, potion.id].includes(target);
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
              <h3>结论</h3>
              <p class="reply-conclusion">{{ activeReply.conclusion }}</p>
            </section>

            <section class="reply-card">
              <div class="reply-header">
                <h3>原因</h3>
                <span v-if="activeReply.build_direction" class="reply-tag">构筑方向：{{ activeReply.build_direction }}</span>
              </div>
              <ul class="reason-list">
                <li v-for="reason in activeReply.reasons" :key="reason">{{ reason }}</li>
              </ul>
            </section>

            <section class="reply-card">
              <h3>备选</h3>
              <div v-if="activeReply.alternatives.length" class="tag-row">
                <span v-for="item in activeReply.alternatives" :key="item" class="tag">{{ item }}</span>
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
                <p class="chat-time">{{ formatTimestamp(item.created_at) }}</p>
              </article>
              <div v-if="!chatHistory.length" class="chat-empty">
                这里会保留本局最近 8 轮问答。
              </div>
            </div>

            <div class="chat-compose">
              <textarea
                v-model="chatInput"
                rows="3"
                placeholder="例如：这层商店先删打击还是留钱？"
                @keydown.enter.exact.prevent="sendChat"
              />
              <button type="button" class="primary-button" :disabled="!canSendChat" @click="sendChat">
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
                  <strong>{{ card.display_name }}</strong>
                  <span>#{{ card.choice_index }}</span>
                </div>
                <p>{{ card.type ?? "未知类型" }} / {{ card.rarity ?? "未知稀有度" }}</p>
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
                    <strong>{{ card.display_name }}</strong>
                    <span>{{ card.price ?? "?" }}g</span>
                  </div>
                  <p>{{ card.type ?? "未知类型" }} / {{ card.rarity ?? "未知稀有度" }}</p>
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
                    <strong>{{ relic.name }}</strong>
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
                    <strong>{{ potion.name }}</strong>
                    <span>{{ potion.price ?? "?" }}g</span>
                  </div>
                </article>
              </div>
            </section>
          </template>

          <template v-else>
            <div class="empty-card">
              <p>当前不在奖励或商店界面，助手仍然可以用于地图、事件和战斗阶段分析。</p>
            </div>
          </template>

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
                <strong>{{ card.display_name }}</strong>
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
              <span v-for="relic in latestState?.relics ?? []" :key="relic.id" class="tag">{{ relic.name }}</span>
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
}
</style>
