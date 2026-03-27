package com.stsassistant.mod;

import basemod.BaseMod;
import basemod.interfaces.PostRenderSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import com.megacrit.cardcrawl.helpers.input.InputHelper;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CompletableFuture;

@SpireInitializer
public class StsIngameAssistantMod implements PostUpdateSubscriber, PostRenderSubscriber {
    private static final int KEY_TOGGLE = Input.Keys.F8;
    private static final int KEY_ANALYZE = Input.Keys.F9;
    private static final int KEY_ESCAPE = Input.Keys.ESCAPE;
    private static final int KEY_ENTER = Input.Keys.ENTER;
    private static final int KEY_BACKSPACE = Input.Keys.BACKSPACE;
    private static final String API_BASE = "http://127.0.0.1:8765";
    private static final Color PANEL_BG = new Color(0.10f, 0.07f, 0.05f, 0.92f);
    private static final Color PANEL_LINE = new Color(0.80f, 0.60f, 0.34f, 0.85f);

    private boolean overlayVisible = false;
    private boolean analyzeKeyConsumed = false;
    private boolean toggleKeyConsumed = false;
    private boolean escapeKeyConsumed = false;
    private boolean enterKeyConsumed = false;
    private boolean backspaceKeyConsumed = false;
    private boolean requestInFlight = false;

    private String connectionStatus = "助手未连接";
    private AssistantReply latestReply = AssistantReply.empty();
    private final List<ChatItem> chatHistory = new ArrayList<ChatItem>();
    private final StringBuilder inputBuffer = new StringBuilder();

    public static void initialize() {
        new StsIngameAssistantMod();
    }

    public StsIngameAssistantMod() {
        BaseMod.subscribe(this);
    }

    @Override
    public void receivePostUpdate() {
        handleToggleKey();
        if (!overlayVisible) {
            return;
        }

        handleAnalyzeKey();
        handleEscapeKey();
        handleBackspaceKey();
        handleCharacterInput();
        handleEnterKey();
    }

    @Override
    public void receivePostRender(SpriteBatch sb) {
        if (!overlayVisible) {
            return;
        }

        float scale = Settings.scale;
        float x = 80.0f * scale;
        float y = 90.0f * scale;
        float w = 950.0f * scale;
        float h = 620.0f * scale;

        sb.setColor(PANEL_BG);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, x, y, w, h);
        sb.setColor(PANEL_LINE);
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, x, y + h - 4.0f * scale, w, 4.0f * scale);
        sb.setColor(Color.WHITE);

        float lineX = x + 28.0f * scale;
        float lineY = y + h - 42.0f * scale;
        drawText(sb, "杀戮尖塔 AI 助手", lineX, lineY, Settings.GOLD_COLOR);
        drawSmallText(sb, "F8 开关  |  F9 分析  |  Enter 发送  |  Esc 关闭", lineX, lineY - 36.0f * scale, Settings.CREAM_COLOR);
        drawSmallText(sb, "连接状态：" + connectionStatus, lineX, lineY - 70.0f * scale, Settings.GREEN_TEXT_COLOR);

        float sectionY = lineY - 126.0f * scale;
        drawText(sb, "结论", lineX, sectionY, Settings.GOLD_COLOR);
        drawWrapped(sb, latestReply.conclusion, lineX, sectionY - 14.0f * scale, w - 56.0f * scale);

        float reasonY = sectionY - 104.0f * scale;
        drawText(sb, "原因", lineX, reasonY, Settings.GOLD_COLOR);
        float reasonLineY = reasonY - 14.0f * scale;
        for (String reason : latestReply.reasons) {
            drawWrapped(sb, "- " + reason, lineX, reasonLineY, w - 56.0f * scale);
            reasonLineY -= 28.0f * scale;
        }

        float altY = reasonY - 128.0f * scale;
        drawText(sb, "备选", lineX, altY, Settings.GOLD_COLOR);
        String alternatives = latestReply.alternatives.isEmpty() ? "暂无" : join(latestReply.alternatives, " / ");
        drawWrapped(sb, alternatives, lineX, altY - 14.0f * scale, w - 56.0f * scale);

        float chatY = altY - 88.0f * scale;
        drawText(sb, "最近问答", lineX, chatY, Settings.GOLD_COLOR);
        float chatLineY = chatY - 14.0f * scale;
        List<ChatItem> recent = new ArrayList<ChatItem>(chatHistory);
        Collections.reverse(recent);
        int shown = 0;
        for (ChatItem item : recent) {
            drawWrapped(sb, "问：" + item.question, lineX, chatLineY, w - 56.0f * scale);
            chatLineY -= 24.0f * scale;
            drawWrapped(sb, "答：" + item.answer, lineX, chatLineY, w - 56.0f * scale);
            chatLineY -= 34.0f * scale;
            shown += 1;
            if (shown >= 3) {
                break;
            }
        }
        if (shown == 0) {
            drawWrapped(sb, "暂无聊天记录", lineX, chatLineY, w - 56.0f * scale);
        }

        float inputY = y + 42.0f * scale;
        drawText(sb, "输入问题", lineX, inputY + 36.0f * scale, Settings.GOLD_COLOR);
        sb.setColor(new Color(1.0f, 1.0f, 1.0f, 0.08f));
        sb.draw(ImageMaster.WHITE_SQUARE_IMG, lineX - 8.0f * scale, inputY - 4.0f * scale, w - 56.0f * scale, 42.0f * scale);
        sb.setColor(Color.WHITE);
        String prompt = inputBuffer.length() == 0 ? "在这里输入你想问的问题..." : inputBuffer.toString();
        drawWrapped(sb, prompt, lineX, inputY + 20.0f * scale, w - 72.0f * scale);
    }

    private void handleToggleKey() {
        boolean pressed = Gdx.input.isKeyPressed(KEY_TOGGLE);
        if (pressed && !toggleKeyConsumed) {
            overlayVisible = !overlayVisible;
            toggleKeyConsumed = true;
        } else if (!pressed) {
            toggleKeyConsumed = false;
        }
    }

    private void handleAnalyzeKey() {
        boolean pressed = Gdx.input.isKeyPressed(KEY_ANALYZE);
        if (pressed && !analyzeKeyConsumed) {
            triggerAnalyze();
            analyzeKeyConsumed = true;
        } else if (!pressed) {
            analyzeKeyConsumed = false;
        }
    }

    private void handleEscapeKey() {
        boolean pressed = Gdx.input.isKeyPressed(KEY_ESCAPE);
        if (pressed && !escapeKeyConsumed) {
            overlayVisible = false;
            escapeKeyConsumed = true;
        } else if (!pressed) {
            escapeKeyConsumed = false;
        }
    }

    private void handleEnterKey() {
        boolean pressed = Gdx.input.isKeyPressed(KEY_ENTER);
        if (pressed && !enterKeyConsumed) {
            sendChat();
            enterKeyConsumed = true;
        } else if (!pressed) {
            enterKeyConsumed = false;
        }
    }

    private void handleBackspaceKey() {
        boolean pressed = Gdx.input.isKeyPressed(KEY_BACKSPACE);
        if (pressed && !backspaceKeyConsumed) {
            if (inputBuffer.length() > 0) {
                inputBuffer.deleteCharAt(inputBuffer.length() - 1);
            }
            backspaceKeyConsumed = true;
        } else if (!pressed) {
            backspaceKeyConsumed = false;
        }
    }

    private void handleCharacterInput() {
        if (InputHelper.pressedKeys == null) {
            return;
        }
        for (char c : InputHelper.pressedKeys) {
            if (Character.isISOControl(c)) {
                continue;
            }
            if (inputBuffer.length() >= 120) {
                break;
            }
            inputBuffer.append(c);
        }
        InputHelper.pressedKeys.clear();
    }

    private void triggerAnalyze() {
        if (requestInFlight) {
            return;
        }
        requestInFlight = true;
        connectionStatus = "正在分析...";
        CompletableFuture
            .supplyAsync(() -> postJson("/api/assistant/analyze", "{\"source\":\"ingame\"}"))
            .thenAccept(this::applyAssistantReply)
            .exceptionally(ex -> {
                connectionStatus = "助手未连接";
                latestReply = AssistantReply.error("分析请求失败");
                requestInFlight = false;
                return null;
            });
    }

    private void sendChat() {
        if (requestInFlight) {
            return;
        }
        String question = inputBuffer.toString().trim();
        if (question.isEmpty()) {
            return;
        }
        requestInFlight = true;
        connectionStatus = "正在询问...";
        String escaped = question.replace("\\", "\\\\").replace("\"", "\\\"");
        String body = "{\"source\":\"ingame\",\"message\":\"" + escaped + "\"}";
        CompletableFuture
            .supplyAsync(() -> postJson("/api/assistant/chat", body))
            .thenAccept(reply -> {
                applyAssistantReply(reply);
                chatHistory.add(new ChatItem(question, latestReply.conclusion));
                while (chatHistory.size() > 8) {
                    chatHistory.remove(0);
                }
                inputBuffer.setLength(0);
            })
            .exceptionally(ex -> {
                connectionStatus = "助手未连接";
                latestReply = AssistantReply.error("聊天请求失败");
                requestInFlight = false;
                return null;
            });
    }

    private void applyAssistantReply(String json) {
        latestReply = AssistantReply.fromJson(json);
        connectionStatus = "助手已连接";
        requestInFlight = false;
    }

    private String postJson(String path, String body) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL(API_BASE + path);
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(3000);
            connection.setReadTimeout(5000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            byte[] payload = body.getBytes(StandardCharsets.UTF_8);
            OutputStream os = connection.getOutputStream();
            os.write(payload);
            os.flush();
            os.close();

            BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder response = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                response.append(line);
            }
            reader.close();
            return response.toString();
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private void drawText(SpriteBatch sb, String text, float x, float y, Color color) {
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.panelNameFont, text, x, y, color);
    }

    private void drawSmallText(SpriteBatch sb, String text, float x, float y, Color color) {
        FontHelper.renderFontLeftTopAligned(sb, FontHelper.cardDescFont_N, text, x, y, color);
    }

    private void drawWrapped(SpriteBatch sb, String text, float x, float y, float width) {
        FontHelper.renderSmartText(sb, FontHelper.cardDescFont_N, text, x, y, width, 28.0f * Settings.scale, Settings.CREAM_COLOR);
    }

    private String join(List<String> items, String delimiter) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) {
                builder.append(delimiter);
            }
            builder.append(items.get(i));
        }
        return builder.toString();
    }

    private static class ChatItem {
        final String question;
        final String answer;

        ChatItem(String question, String answer) {
            this.question = question;
            this.answer = answer;
        }
    }

    private static class AssistantReply {
        final String conclusion;
        final List<String> reasons;
        final List<String> alternatives;

        AssistantReply(String conclusion, List<String> reasons, List<String> alternatives) {
            this.conclusion = conclusion;
            this.reasons = reasons;
            this.alternatives = alternatives;
        }

        static AssistantReply empty() {
            return new AssistantReply(
                "按 F9 可以请求当前局面分析。",
                Collections.singletonList("助手会在这里显示中文结论与取舍理由。"),
                new ArrayList<String>()
            );
        }

        static AssistantReply error(String conclusion) {
            return new AssistantReply(
                conclusion,
                Collections.singletonList("请确认 Python 后端已启动，并且 http://127.0.0.1:8765 可以访问。"),
                new ArrayList<String>()
            );
        }

        static AssistantReply fromJson(String json) {
            return new AssistantReply(
                extractString(json, "conclusion", "暂无结论"),
                extractArray(json, "reasons"),
                extractArray(json, "alternatives")
            );
        }

        private static String extractString(String json, String key, String fallback) {
            String marker = "\"" + key + "\":";
            int start = json.indexOf(marker);
            if (start < 0) {
                return fallback;
            }
            start = json.indexOf('"', start + marker.length());
            if (start < 0) {
                return fallback;
            }
            start += 1;
            StringBuilder builder = new StringBuilder();
            boolean escaping = false;
            for (int i = start; i < json.length(); i++) {
                char c = json.charAt(i);
                if (escaping) {
                    builder.append(c);
                    escaping = false;
                    continue;
                }
                if (c == '\\') {
                    escaping = true;
                    continue;
                }
                if (c == '"') {
                    break;
                }
                builder.append(c);
            }
            return builder.toString();
        }

        private static List<String> extractArray(String json, String key) {
            String marker = "\"" + key + "\":";
            int start = json.indexOf(marker);
            if (start < 0) {
                return new ArrayList<String>();
            }
            start = json.indexOf('[', start + marker.length());
            if (start < 0) {
                return new ArrayList<String>();
            }
            int end = json.indexOf(']', start);
            if (end < 0) {
                return new ArrayList<String>();
            }
            String body = json.substring(start + 1, end).trim();
            if (body.isEmpty()) {
                return new ArrayList<String>();
            }
            String[] parts = body.split(",");
            List<String> values = new ArrayList<String>();
            for (String part : parts) {
                String value = part.trim();
                if (value.startsWith("\"")) {
                    value = value.substring(1);
                }
                if (value.endsWith("\"")) {
                    value = value.substring(0, value.length() - 1);
                }
                value = value.replace("\\\"", "\"");
                if (!value.isEmpty()) {
                    values.add(value);
                }
            }
            return values;
        }
    }
}
