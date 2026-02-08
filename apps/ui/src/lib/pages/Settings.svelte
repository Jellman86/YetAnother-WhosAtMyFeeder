<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import {
        fetchSettings,
        updateSettings,
        testFrigateConnection,
        fetchFrigateConfig,
        fetchClassifierStatus,
        downloadDefaultModel,
        fetchWildlifeModelStatus,
        downloadWildlifeModel,
        fetchMaintenanceStats,
        runCleanup,
        purgeMissingClips,
        purgeMissingSnapshots,
        runBackfill,
        runWeatherBackfill,
        startBackfillJob,
        startWeatherBackfillJob,
        getBackfillStatus,
        fetchCacheStats,
        runCacheCleanup,
        fetchTaxonomyStatus,
        startTaxonomySync,
        resetDatabase,
        analyzeUnknowns,
        fetchAnalysisStatus,
        testBirdWeather,
        testLlm,
        testBirdNET,
        testMQTTPublish,
        testNotification,
        fetchVersion,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        sendTestEmail,
        exportEbirdCsv,
        type ClassifierStatus,
        type WildlifeModelStatus,
        type MaintenanceStats,
        type BackfillResult,
        type WeatherBackfillResult,
        type BackfillJobStatus,
        type CacheStats,
        type CacheCleanupResult,
        type TaxonomySyncStatus,
        type VersionInfo
    } from '../api';
    import { themeStore, type Theme } from '../stores/theme.svelte';
    import { layoutStore, type Layout } from '../stores/layout.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { _, locale } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import SettingsTabs from '../components/settings/SettingsTabs.svelte';

    // Import all 7 settings components
    import AccessibilitySettings from '../components/settings/AccessibilitySettings.svelte';
    import AppearanceSettings from '../components/settings/AppearanceSettings.svelte';
    import ConnectionSettings from '../components/settings/ConnectionSettings.svelte';
    import DetectionSettings from '../components/settings/DetectionSettings.svelte';
    import DataSettings from '../components/settings/DataSettings.svelte';
    import EnrichmentSettings from '../components/settings/EnrichmentSettings.svelte';
    import IntegrationSettings from '../components/settings/IntegrationSettings.svelte';
    import NotificationSettings from '../components/settings/NotificationSettings.svelte';
    import AuthenticationSettings from '../components/settings/AuthenticationSettings.svelte';

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let audioTopic = $state('birdnet/text');
    let cameraAudioMapping = $state<Record<string, string>>({});
    let audioBufferHours = $state(24);
    let audioCorrelationWindowSeconds = $state(300);
    let clipsEnabled = $state(true);
    let threshold = $state(0.7);
    let minConfidence = $state(0.4);
    let trustFrigateSublabel = $state(true);
    let displayCommonNames = $state(true);
    let scientificNamePrimary = $state(false);
    let autoVideoClassification = $state(false);
    let videoClassificationDelay = $state(30);
    let videoClassificationMaxRetries = $state(3);
    let videoCircuitOpen = $state(false);
    let videoCircuitUntil = $state<string | null>(null);
    let videoCircuitFailures = $state(0);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);
    let blockedLabels = $state<string[]>([]);
    let newBlockedLabel = $state('');

    // Taxonomy Sync State
    let taxonomyStatus = $state<TaxonomySyncStatus | null>(null);
    let syncingTaxonomy = $state(false);
    let taxonomyPollInterval: any;

    // Location Settings
    let locationLat = $state<number | null>(null);
    let locationLon = $state<number | null>(null);
    let locationAuto = $state(true);
    let locationTemperatureUnit = $state<'celsius' | 'fahrenheit'>('celsius');

    // BirdNET-Go Settings
    let birdnetEnabled = $state(true);

    // BirdWeather Settings
    let birdweatherEnabled = $state(false);
    let birdweatherStationToken = $state('');

    // iNaturalist Settings
    let inaturalistEnabled = $state(false);
    let inaturalistClientId = $state('');
    let inaturalistClientSecret = $state('');
    let inaturalistClientIdSaved = $state(false);
    let inaturalistClientSecretSaved = $state(false);
    let inaturalistDefaultLat = $state<number | null>(null);
    let inaturalistDefaultLon = $state<number | null>(null);
    let inaturalistDefaultPlace = $state('');
    let inaturalistConnectedUser = $state<string | null>(null);

    // LLM Settings
    let llmEnabled = $state(false);
    let llmProvider = $state('gemini');
    let llmApiKey = $state('');
    let llmModel = $state('gemini-2.5-flash');
    let llmAnalysisPromptTemplate = $state('');
    let llmConversationPromptTemplate = $state('');
    let llmChartPromptTemplate = $state('');
    let llmPromptStyle = $state('classic');

    const promptTemplates = {
        classic: {
            en: {
                analysis: `You are an expert ornithologist and naturalist.
{frame_note}

Species identified by system: {species}
Time of detection: {time}
{weather_str}

Respond in Markdown with these exact section headings. Under each heading, write 1 short paragraph (or up to 3 bullets if it helps scanning):
## Appearance
## Behavior
## Naturalist Note
## Seasonal Context

Keep the response concise (under 200 words). No extra sections.
{language_note}`.trim(),
                conversation: `You are an expert ornithologist and naturalist. Continue a short Q&A about this detection.

Species identified by system: {species}
Previous analysis:
{analysis}

Conversation so far:
{history}

User question: {question}

Answer concisely in Markdown using the same headings as the analysis (## Appearance, ## Behavior, ## Naturalist Note, ## Seasonal Context).
If a section is not relevant, include it with a short "Not observed." line.
{language_note}`.trim(),
                chart: `You are a data analyst for bird feeder activity.
You are looking at a chart of detections over time.

Timeframe: {timeframe}
Total detections in range: {total_count}
Series shown: {series}
{weather_notes}
{sun_notes}

Respond in Markdown with these exact section headings and short bullet points:
## Overview
## Patterns
## Weather Correlations
## Notable Spikes/Dips
## Caveats

Keep it concise (under 200 words). No extra sections.
{language_note}
{notes}`.trim()
            },
            es: {
                analysis: `Eres un ornitólogo y naturalista experto.
{frame_note}

Especie identificada por el sistema: {species}
Hora de detección: {time}
{weather_str}

Responde en Markdown con estos encabezados exactos y viñetas breves:
## Apariencia
## Comportamiento
## Nota de naturalista
## Contexto estacional

Mantén la respuesta concisa (menos de 200 palabras). Sin secciones adicionales.
{language_note}`.trim(),
                conversation: `Eres un ornitólogo y naturalista experto. Continúa una breve sesión de preguntas y respuestas sobre esta detección.

Especie identificada por el sistema: {species}
Análisis previo:
{analysis}

Conversación hasta ahora:
{history}

Pregunta del usuario: {question}

Responde de forma concisa en Markdown usando los mismos encabezados que el análisis (## Apariencia, ## Comportamiento, ## Nota de naturalista, ## Contexto estacional).
Si una sección no es relevante, inclúyela con una viñeta breve de "No observado".
{language_note}`.trim(),
                chart: `Eres un analista de actividad de comederos de aves.
Estás viendo un gráfico de detecciones a lo largo del tiempo.

Periodo: {timeframe}
Detecciones totales en el rango: {total_count}
Series mostradas: {series}
{weather_notes}
{sun_notes}

Responde en Markdown con estos encabezados exactos y viñetas breves:
## Resumen
## Patrones
## Correlaciones con el clima
## Picos/caídas notables
## Consideraciones

Mantén la respuesta concisa (menos de 200 palabras). Sin secciones adicionales.
{language_note}
{notes}`.trim()
            },
            fr: {
                analysis: `Vous êtes un ornithologue et naturaliste expert.
{frame_note}

Espèce identifiée par le système : {species}
Heure de détection : {time}
{weather_str}

Répondez en Markdown avec ces titres exacts et des puces courtes :
## Apparence
## Comportement
## Note de naturaliste
## Contexte saisonnier

Restez concis (moins de 200 mots). Aucune section supplémentaire.
{language_note}`.trim(),
                conversation: `Vous êtes un ornithologue et naturaliste expert. Poursuivez un court échange Q/R sur cette détection.

Espèce identifiée par le système : {species}
Analyse précédente :
{analysis}

Conversation jusqu'à présent :
{history}

Question de l'utilisateur : {question}

Répondez brièvement en Markdown avec les mêmes titres que l'analyse (## Apparence, ## Comportement, ## Note de naturaliste, ## Contexte saisonnier).
Si une section n'est pas pertinente, incluez-la avec une puce courte « Non observé ».
{language_note}`.trim(),
                chart: `Vous êtes analyste des activités d'un nourrisseur d'oiseaux.
Vous regardez un graphique des détections dans le temps.

Période : {timeframe}
Détections totales : {total_count}
Séries affichées : {series}
{weather_notes}
{sun_notes}

Répondez en Markdown avec ces titres exacts et des puces courtes :
## Aperçu
## Tendances
## Corrélations météo
## Pics/creux notables
## Limites

Restez concis (moins de 200 mots). Aucune section supplémentaire.
{language_note}
{notes}`.trim()
            },
            de: {
                analysis: `Du bist ein*e erfahrene*r Ornithologe*in und Naturkundler*in.
{frame_note}

Vom System identifizierte Art: {species}
Erkennungszeit: {time}
{weather_str}

Antworte in Markdown mit genau diesen Überschriften und kurzen Stichpunkten:
## Erscheinung
## Verhalten
## Naturkundliche Notiz
## Saisonaler Kontext

Halte die Antwort kurz (unter 200 Wörtern). Keine zusätzlichen Abschnitte.
{language_note}`.trim(),
                conversation: `Du bist ein*e erfahrene*r Ornithologe*in und Naturkundler*in. Führe eine kurze Q&A zu dieser Erkennung fort.

Vom System identifizierte Art: {species}
Vorherige Analyse:
{analysis}

Bisherige Unterhaltung:
{history}

Nutzerfrage: {question}

Antworte kurz in Markdown mit denselben Überschriften wie die Analyse (## Erscheinung, ## Verhalten, ## Naturkundliche Notiz, ## Saisonaler Kontext).
Wenn ein Abschnitt nicht relevant ist, füge ihn mit einem kurzen Stichpunkt „Nicht beobachtet“ hinzu.
{language_note}`.trim(),
                chart: `Du bist Datenanalyst*in für Aktivitäten am Vogelhäuschen.
Du siehst ein Diagramm der Erkennungen über die Zeit.

Zeitraum: {timeframe}
Gesamterkennungen im Zeitraum: {total_count}
Angezeigte Reihen: {series}
{weather_notes}
{sun_notes}

Antworte in Markdown mit genau diesen Überschriften und kurzen Stichpunkten:
## Überblick
## Muster
## Wetterkorrelationen
## Auffällige Spitzen/Täler
## Einschränkungen

Halte die Antwort kurz (unter 200 Wörter). Keine zusätzlichen Abschnitte.
{language_note}
{notes}`.trim()
            },
            it: {
                analysis: `Sei un esperto ornitologo e naturalista.
{frame_note}

Specie identificata dal sistema: {species}
Ora della rilevazione: {time}
{weather_str}

Rispondi in Markdown con questi titoli esatti e punti elenco brevi:
## Aspetto
## Comportamento
## Nota naturalistica
## Contesto stagionale

Mantieni la risposta concisa (meno di 200 parole). Nessuna sezione extra.
{language_note}`.trim(),
                conversation: `Sei un esperto ornitologo e naturalista. Continua una breve Q&A su questa rilevazione.

Specie identificata dal sistema: {species}
Analisi precedente:
{analysis}

Conversazione finora:
{history}

Domanda dell'utente: {question}

Rispondi brevemente in Markdown usando gli stessi titoli dell'analisi (## Aspetto, ## Comportamento, ## Nota naturalistica, ## Contesto stagionale).
Se una sezione non è pertinente, includila con un punto breve "Non osservato".
{language_note}`.trim(),
                chart: `Sei un analista dei dati per l'attività al feeder.
Stai guardando un grafico delle rilevazioni nel tempo.

Periodo: {timeframe}
Rilevazioni totali: {total_count}
Serie mostrate: {series}
{weather_notes}
{sun_notes}

Rispondi in Markdown con questi titoli esatti e punti elenco brevi:
## Panoramica
## Andamenti
## Correlazioni meteo
## Picchi/cali notevoli
## Avvertenze

Mantieni la risposta concisa (meno di 200 parole). Nessuna sezione extra.
{language_note}
{notes}`.trim()
            },
            pt: {
                analysis: `Você é um ornitólogo e naturalista experiente.
{frame_note}

Espécie identificada pelo sistema: {species}
Hora da detecção: {time}
{weather_str}

Responda em Markdown com estes títulos exatos e tópicos curtos:
## Aparência
## Comportamento
## Nota naturalista
## Contexto sazonal

Mantenha a resposta concisa (menos de 200 palavras). Sem seções extras.
{language_note}`.trim(),
                conversation: `Você é um ornitólogo e naturalista experiente. Continue uma breve sessão de perguntas e respostas sobre esta detecção.

Espécie identificada pelo sistema: {species}
Análise anterior:
{analysis}

Conversa até agora:
{history}

Pergunta do usuário: {question}

Responda de forma concisa em Markdown usando os mesmos títulos da análise (## Aparência, ## Comportamento, ## Nota naturalista, ## Contexto sazonal).
Se uma seção não for relevante, inclua-a com um tópico curto \"Não observado\".
{language_note}`.trim(),
                chart: `Você é um analista de atividade em comedouros de aves.
Você está olhando para um gráfico de detecções ao longo do tempo.

Período: {timeframe}
Detecções totais no período: {total_count}
Séries exibidas: {series}
{weather_notes}
{sun_notes}

Responda em Markdown com estes títulos exatos e tópicos curtos:
## Visão geral
## Padrões
## Correlações climáticas
## Picos/queda notáveis
## Observações

Mantenha a resposta concisa (menos de 200 palavras). Sem seções extras.
{language_note}
{notes}`.trim()
            },
            ja: {
                analysis: `あなたは熟練した鳥類学者・ナチュラリストです。
{frame_note}

システムが特定した種: {species}
検出時刻: {time}
{weather_str}

以下の見出しを必ず使い、短い箇条書きでMarkdownで回答してください:
## 外見
## 行動
## ナチュラリストのメモ
## 季節的な背景

簡潔に（200語未満）。追加セクションは不要です。
{language_note}`.trim(),
                conversation: `あなたは熟練した鳥類学者・ナチュラリストです。この検出について短いQ&Aを続けてください。

システムが特定した種: {species}
以前の分析:
{analysis}

これまでの会話:
{history}

ユーザーの質問: {question}

分析と同じ見出し（## 外見, ## 行動, ## ナチュラリストのメモ, ## 季節的な背景）を使い、簡潔にMarkdownで回答してください。
該当しない見出しは「観察されず」の短い箇条書きを入れてください。
{language_note}`.trim(),
                chart: `あなたは野鳥の餌台の活動を分析するデータアナリストです。
時間に沿った検出数のグラフを見ています。

期間: {timeframe}
総検出数: {total_count}
表示系列: {series}
{weather_notes}
{sun_notes}

以下の見出しを必ず使い、短い箇条書きでMarkdownで回答してください:
## 概要
## パターン
## 天候との相関
## 目立つ増減
## 注意点

簡潔に（200語未満）。追加セクションは不要です。
{language_note}
{notes}`.trim()
            },
            ru: {
                analysis: `Вы — опытный орнитолог и натуралист.
{frame_note}

Вид, определённый системой: {species}
Время обнаружения: {time}
{weather_str}

Ответьте в Markdown с точными заголовками и краткими пунктами:
## Внешний вид
## Поведение
## Заметка натуралиста
## Сезонный контекст

Ответ должен быть кратким (до 200 слов). Без дополнительных разделов.
{language_note}`.trim(),
                conversation: `Вы — опытный орнитолог и натуралист. Продолжите короткое Q&A об этой детекции.

Вид, определённый системой: {species}
Предыдущий анализ:
{analysis}

Диалог до сих пор:
{history}

Вопрос пользователя: {question}

Отвечайте кратко в Markdown, используя те же заголовки, что и в анализе (## Внешний вид, ## Поведение, ## Заметка натуралиста, ## Сезонный контекст).
Если раздел не актуален, добавьте короткий пункт «Не наблюдалось».
{language_note}`.trim(),
                chart: `Вы — аналитик активности у кормушки.
Вы смотрите на график детекций во времени.

Период: {timeframe}
Всего детекций: {total_count}
Показанные серии: {series}
{weather_notes}
{sun_notes}

Ответьте в Markdown с точными заголовками и краткими пунктами:
## Обзор
## Паттерны
## Корреляции с погодой
## Заметные пики/спады
## Ограничения

Ответ должен быть кратким (до 200 слов). Без дополнительных разделов.
{language_note}
{notes}`.trim()
            },
            zh: {
                analysis: `你是一名经验丰富的鸟类学家和自然观察者。
{frame_note}

系统识别物种：{species}
检测时间：{time}
{weather_str}

请用Markdown回答，并严格使用以下标题和简短要点：
## 外观
## 行为
## 自然观察笔记
## 季节背景

保持简洁（少于200词）。不要添加额外章节。
{language_note}`.trim(),
                conversation: `你是一名经验丰富的鸟类学家和自然观察者。继续围绕这次检测进行简短问答。

系统识别物种：{species}
之前的分析：
{analysis}

对话记录：
{history}

用户问题：{question}

请用Markdown简洁回答，并使用与分析相同的标题（## 外观, ## 行为, ## 自然观察笔记, ## 季节背景）。
若某部分不适用，请添加“未观察到”的简短要点。
{language_note}`.trim(),
                chart: `你是一名喂鸟器活动的数据分析师。
你正在查看随时间变化的检测图表。

时间范围：{timeframe}
总检测数：{total_count}
显示序列：{series}
{weather_notes}
{sun_notes}

请用Markdown回答，并严格使用以下标题和简短要点：
## 概览
## 模式
## 天气相关性
## 显著峰谷
## 注意事项

保持简洁（少于200词）。不要添加额外章节。
{language_note}
{notes}`.trim()
            }
        },
        field: {
            en: {
                analysis: `You are an expert ornithologist writing field notes.
{frame_note}

Species identified by system: {species}
Time of detection: {time}
{weather_str}

Respond in Markdown with these exact section headings and 1–3 short bullet points per section:
## Appearance
## Behavior
## Naturalist Note
## Seasonal Context

Use vivid but factual language. Keep under 200 words. No extra sections.
{language_note}`.trim(),
                conversation: `You are an expert ornithologist writing field notes. Continue a short Q&A about this detection.

Species identified by system: {species}
Previous analysis:
{analysis}

Conversation so far:
{history}

User question: {question}

Answer concisely in Markdown using the same headings as the analysis (## Appearance, ## Behavior, ## Naturalist Note, ## Seasonal Context).
If a section is not relevant, include it with a short "Not observed" bullet.
{language_note}`.trim(),
                chart: `You are a data analyst for bird feeder activity.
You are looking at a chart of detections over time.

Timeframe: {timeframe}
Total detections in range: {total_count}
Series shown: {series}
{weather_notes}
{sun_notes}

Respond in Markdown with these exact section headings and short bullet points:
## Overview
## Patterns
## Weather Correlations
## Notable Spikes/Dips
## Caveats

Keep it concise (under 200 words). No extra sections.
{language_note}
{notes}`.trim()
            },
            es: {
                analysis: `Eres un ornitólogo experto que escribe notas de campo.
{frame_note}

Especie identificada por el sistema: {species}
Hora de detección: {time}
{weather_str}

Responde en Markdown con estos encabezados exactos y 1–3 viñetas breves por sección:
## Apariencia
## Comportamiento
## Nota de naturalista
## Contexto estacional

Usa un lenguaje vívido pero factual. Menos de 200 palabras. Sin secciones extra.
{language_note}`.trim(),
                conversation: `Eres un ornitólogo experto que escribe notas de campo. Continúa una breve Q&A sobre esta detección.

Especie identificada por el sistema: {species}
Análisis previo:
{analysis}

Conversación hasta ahora:
{history}

Pregunta del usuario: {question}

Responde de forma concisa en Markdown con los mismos encabezados del análisis (## Apariencia, ## Comportamiento, ## Nota de naturalista, ## Contexto estacional).
Si una sección no es relevante, incluye una viñeta breve de \"No observado\".
{language_note}`.trim(),
                chart: `Eres un analista de actividad en comederos de aves.
Estás viendo un gráfico de detecciones a lo largo del tiempo.

Periodo: {timeframe}
Detecciones totales en el rango: {total_count}
Series mostradas: {series}
{weather_notes}
{sun_notes}

Responde en Markdown con estos encabezados exactos y viñetas breves:
## Resumen
## Patrones
## Correlaciones con el clima
## Picos/caídas notables
## Consideraciones

Mantén la respuesta concisa (menos de 200 palabras). Sin secciones adicionales.
{language_note}
{notes}`.trim()
            },
            fr: {
                analysis: `Vous êtes un ornithologue expert qui rédige des notes de terrain.
{frame_note}

Espèce identifiée par le système : {species}
Heure de détection : {time}
{weather_str}

Répondez en Markdown avec ces titres exacts et 1–3 puces courtes par section :
## Apparence
## Comportement
## Note de naturaliste
## Contexte saisonnier

Langage vivant mais factuel. Moins de 200 mots. Pas de sections supplémentaires.
{language_note}`.trim(),
                conversation: `Vous êtes un ornithologue expert qui rédige des notes de terrain. Poursuivez une courte Q/R sur cette détection.

Espèce identifiée par le système : {species}
Analyse précédente :
{analysis}

Conversation jusqu'à présent :
{history}

Question de l'utilisateur : {question}

Répondez brièvement en Markdown avec les mêmes titres que l'analyse (## Apparence, ## Comportement, ## Note de naturaliste, ## Contexte saisonnier).
Si un titre n'est pas pertinent, ajoutez une puce courte « Non observé ».
{language_note}`.trim(),
                chart: `Vous êtes analyste des activités d'un nourrisseur d'oiseaux.
Vous regardez un graphique des détections dans le temps.

Période : {timeframe}
Détections totales : {total_count}
Séries affichées : {series}
{weather_notes}
{sun_notes}

Répondez en Markdown avec ces titres exacts et des puces courtes :
## Aperçu
## Tendances
## Corrélations météo
## Pics/creux notables
## Limites

Restez concis (moins de 200 mots). Aucune section supplémentaire.
{language_note}
{notes}`.trim()
            },
            de: {
                analysis: `Du bist ein*e erfahrene*r Ornithologe*in und schreibst Feldnotizen.
{frame_note}

Vom System identifizierte Art: {species}
Erkennungszeit: {time}
{weather_str}

Antworte in Markdown mit genau diesen Überschriften und 1–3 kurzen Stichpunkten pro Abschnitt:
## Erscheinung
## Verhalten
## Naturkundliche Notiz
## Saisonaler Kontext

Lebendig, aber sachlich. Unter 200 Wörtern. Keine zusätzlichen Abschnitte.
{language_note}`.trim(),
                conversation: `Du bist ein*e erfahrene*r Ornithologe*in und schreibst Feldnotizen. Setze eine kurze Q&A zu dieser Erkennung fort.

Vom System identifizierte Art: {species}
Vorherige Analyse:
{analysis}

Bisherige Unterhaltung:
{history}

Nutzerfrage: {question}

Antworte kurz in Markdown mit denselben Überschriften wie die Analyse (## Erscheinung, ## Verhalten, ## Naturkundliche Notiz, ## Saisonaler Kontext).
Wenn ein Abschnitt nicht relevant ist, füge einen kurzen Stichpunkt „Nicht beobachtet“ hinzu.
{language_note}`.trim(),
                chart: `Du bist Datenanalyst*in für Aktivitäten am Vogelhäuschen.
Du siehst ein Diagramm der Erkennungen über die Zeit.

Zeitraum: {timeframe}
Gesamterkennungen im Zeitraum: {total_count}
Angezeigte Reihen: {series}
{weather_notes}
{sun_notes}

Antworte in Markdown mit genau diesen Überschriften und kurzen Stichpunkten:
## Überblick
## Muster
## Wetterkorrelationen
## Auffällige Spitzen/Täler
## Einschränkungen

Halte die Antwort kurz (unter 200 Wörter). Keine zusätzlichen Abschnitte.
{language_note}
{notes}`.trim()
            },
            it: {
                analysis: `Sei un ornitologo esperto che scrive note di campo.
{frame_note}

Specie identificata dal sistema: {species}
Ora della rilevazione: {time}
{weather_str}

Rispondi in Markdown con questi titoli esatti e 1–3 punti elenco brevi per sezione:
## Aspetto
## Comportamento
## Nota naturalistica
## Contesto stagionale

Linguaggio vivido ma fattuale. Meno di 200 parole. Nessuna sezione extra.
{language_note}`.trim(),
                conversation: `Sei un ornitologo esperto che scrive note di campo. Continua una breve Q&A su questa rilevazione.

Specie identificata dal sistema: {species}
Analisi precedente:
{analysis}

Conversazione finora:
{history}

Domanda dell'utente: {question}

Rispondi brevemente in Markdown usando gli stessi titoli dell'analisi (## Aspetto, ## Comportamento, ## Nota naturalistica, ## Contesto stagionale).
Se una sezione non è pertinente, includi un punto breve \"Non osservato\".
{language_note}`.trim(),
                chart: `Sei un analista dei dati per l'attività al feeder.
Stai guardando un grafico delle rilevazioni nel tempo.

Periodo: {timeframe}
Rilevazioni totali: {total_count}
Serie mostrate: {series}
{weather_notes}
{sun_notes}

Rispondi in Markdown con questi titoli esatti e punti elenco brevi:
## Panoramica
## Andamenti
## Correlazioni meteo
## Picchi/cali notevoli
## Avvertenze

Mantieni la risposta concisa (meno di 200 parole). Nessuna sezione extra.
{language_note}
{notes}`.trim()
            },
            pt: {
                analysis: `Você é um ornitólogo experiente que escreve notas de campo.
{frame_note}

Espécie identificada pelo sistema: {species}
Hora da detecção: {time}
{weather_str}

Responda em Markdown com estes títulos exatos e 1–3 tópicos curtos por seção:
## Aparência
## Comportamento
## Nota naturalista
## Contexto sazonal

Linguagem vívida, porém factual. Menos de 200 palavras. Sem seções extras.
{language_note}`.trim(),
                conversation: `Você é um ornitólogo experiente que escreve notas de campo. Continue uma breve Q&A sobre esta detecção.

Espécie identificada pelo sistema: {species}
Análise anterior:
{analysis}

Conversa até agora:
{history}

Pergunta do usuário: {question}

Responda de forma concisa em Markdown usando os mesmos títulos da análise (## Aparência, ## Comportamento, ## Nota naturalista, ## Contexto sazonal).
Se uma seção não for relevante, inclua um tópico curto \"Não observado\".
{language_note}`.trim(),
                chart: `Você é um analista de atividade em comedouros de aves.
Você está olhando para um gráfico de detecções ao longo do tempo.

Período: {timeframe}
Detecções totais no período: {total_count}
Séries exibidas: {series}
{weather_notes}
{sun_notes}

Responda em Markdown com estes títulos exatos e tópicos curtos:
## Visão geral
## Padrões
## Correlações climáticas
## Picos/queda notáveis
## Observações

Mantenha a resposta concisa (menos de 200 palavras). Sem seções extras.
{language_note}
{notes}`.trim()
            },
            ja: {
                analysis: `あなたは熟練した鳥類学者で、フィールドノートを書いています。
{frame_note}

システムが特定した種: {species}
検出時刻: {time}
{weather_str}

以下の見出しを必ず使い、各セクション1〜3個の短い箇条書きでMarkdown回答:
## 外見
## 行動
## ナチュラリストのメモ
## 季節的な背景

生き生きとしつつ事実に基づいた表現で。200語未満。追加セクション不要。
{language_note}`.trim(),
                conversation: `あなたは熟練した鳥類学者で、フィールドノートを書いています。この検出について短いQ&Aを続けてください。

システムが特定した種: {species}
以前の分析:
{analysis}

これまでの会話:
{history}

ユーザーの質問: {question}

分析と同じ見出し（## 外見, ## 行動, ## ナチュラリストのメモ, ## 季節的な背景）を使い、簡潔にMarkdownで回答してください。
該当しない見出しは「観察されず」の短い箇条書きを入れてください。
{language_note}`.trim(),
                chart: `あなたは野鳥の餌台の活動を分析するデータアナリストです。
時間に沿った検出数のグラフを見ています。

期間: {timeframe}
総検出数: {total_count}
表示系列: {series}
{weather_notes}
{sun_notes}

以下の見出しを必ず使い、短い箇条書きでMarkdownで回答してください:
## 概要
## パターン
## 天候との相関
## 目立つ増減
## 注意点

簡潔に（200語未満）。追加セクションは不要です。
{language_note}
{notes}`.trim()
            },
            ru: {
                analysis: `Вы — опытный орнитолог, пишущий полевые заметки.
{frame_note}

Вид, определённый системой: {species}
Время обнаружения: {time}
{weather_str}

Ответьте в Markdown с точными заголовками и 1–3 короткими пунктами на раздел:
## Внешний вид
## Поведение
## Заметка натуралиста
## Сезонный контекст

Живо, но фактически. До 200 слов. Без дополнительных разделов.
{language_note}`.trim(),
                conversation: `Вы — опытный орнитолог, пишущий полевые заметки. Продолжите короткое Q&A об этой детекции.

Вид, определённый системой: {species}
Предыдущий анализ:
{analysis}

Диалог до сих пор:
{history}

Вопрос пользователя: {question}

Отвечайте кратко в Markdown, используя те же заголовки, что и в анализе (## Внешний вид, ## Поведение, ## Заметка натуралиста, ## Сезонный контекст).
Если раздел не актуален, добавьте короткий пункт «Не наблюдалось».
{language_note}`.trim(),
                chart: `Вы — аналитик активности у кормушки.
Вы смотрите на график детекций во времени.

Период: {timeframe}
Всего детекций: {total_count}
Показанные серии: {series}
{weather_notes}
{sun_notes}

Ответьте в Markdown с точными заголовками и краткими пунктами:
## Обзор
## Паттерны
## Корреляции с погодой
## Заметные пики/спады
## Ограничения

Ответ должен быть кратким (до 200 слов). Без дополнительных разделов.
{language_note}
{notes}`.trim()
            },
            zh: {
                analysis: `你是一名记录野外笔记的鸟类学专家。
{frame_note}

系统识别物种：{species}
检测时间：{time}
{weather_str}

请用Markdown回答，并严格使用以下标题，每个部分1–3个简短要点：
## 外观
## 行为
## 自然观察笔记
## 季节背景

语言生动但保持事实。少于200词。不要添加额外章节。
{language_note}`.trim(),
                conversation: `你是一名记录野外笔记的鸟类学专家。继续围绕这次检测进行简短问答。

系统识别物种：{species}
之前的分析：
{analysis}

对话记录：
{history}

用户问题：{question}

请用Markdown简洁回答，并使用与分析相同的标题（## 外观, ## 行为, ## 自然观察笔记, ## 季节背景）。
若某部分不适用，请添加“未观察到”的简短要点。
{language_note}`.trim(),
                chart: `你是一名喂鸟器活动的数据分析师。
你正在查看随时间变化的检测图表。

时间范围：{timeframe}
总检测数：{total_count}
显示序列：{series}
{weather_notes}
{sun_notes}

请用Markdown回答，并严格使用以下标题和简短要点：
## 概览
## 模式
## 天气相关性
## 显著峰谷
## 注意事项

保持简洁（少于200词）。不要添加额外章节。
{language_note}
{notes}`.trim()
            }
        }
    } as const;

    const resolvePromptLocale = (value: string) => {
        const normalized = value.split('-')[0];
        if (promptTemplates.classic[normalized as keyof typeof promptTemplates.classic]) {
            return normalized;
        }
        return 'en';
    };

    const applyPromptTemplates = (style: keyof typeof promptTemplates = 'classic') => {
        const localeCode = resolvePromptLocale(get(locale) || 'en');
        const templates = promptTemplates[style]?.[localeCode as keyof typeof promptTemplates.classic] || promptTemplates.classic.en;
        llmAnalysisPromptTemplate = templates.analysis;
        llmConversationPromptTemplate = templates.conversation;
        llmChartPromptTemplate = templates.chart;
        toastStore.success($_('settings.debug.llm_prompt_apply_notice', { default: 'Prompt templates updated.' }));
    };

    const resetPromptTemplates = () => {
        llmPromptStyle = 'classic';
        applyPromptTemplates('classic');
    };

    // Available models per provider (Updated February 2026, see provider docs)
    const modelsByProvider = {
        gemini: [
            { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite (Cheapest, Fastest)' },
            { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash (Recommended, Balanced)' },
            { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro (Most capable)' }
        ],
        openai: [
            { value: 'gpt-5-mini', label: 'GPT-5 mini (Cheapest, Fast)' },
            { value: 'gpt-5.2', label: 'GPT-5.2 (Recommended)' },
            { value: 'gpt-5.2-pro', label: 'GPT-5.2 Pro (Most capable)' }
        ],
        claude: [
            { value: 'claude-3-5-haiku-latest', label: 'Claude Haiku 3.5 (Cheapest, Fast)' },
            { value: 'claude-3-5-sonnet-latest', label: 'Claude Sonnet 3.5 (Recommended)' },
            { value: 'claude-3-7-sonnet-latest', label: 'Claude Sonnet 3.7 (Stronger Reasoning)' },
            { value: 'claude-sonnet-4-0', label: 'Claude Sonnet 4 (Most capable, Stable)' },
            { value: 'claude-opus-4-0', label: 'Claude Opus 4 (Most capable, Stable)' }
        ]
    };

    // Get models for current provider
    let availableModels = $derived(modelsByProvider[llmProvider as keyof typeof modelsByProvider] || []);

    // Update model to first available when provider changes
    $effect(() => {
        const models = modelsByProvider[llmProvider as keyof typeof modelsByProvider];
        if (models && models.length > 0) {
            // Check if current model is valid for new provider
            const isValidModel = models.some(m => m.value === llmModel);
            if (!isValidModel) {
                llmModel = models[0].value;
            }
        }
    });

    // Telemetry
    let telemetryEnabled = $state(true);
    let telemetryInstallationId = $state<string | undefined>(undefined);
    let telemetryPlatform = $state<string | undefined>(undefined);

    // Authentication + Public Access
    let authEnabled = $state(false);
    let authUsername = $state('admin');
    let authHasPassword = $state(false);
    let authPassword = $state('');
    let authPasswordConfirm = $state('');
    let authSessionExpiryHours = $state(168);
    let trustedProxyHosts = $state<string[]>([]);
    let trustedProxyHostsSuggested = $state(false);
    let newTrustedProxyHost = $state('');
    let publicAccessEnabled = $state(false);
    let publicAccessShowCameraNames = $state(true);
    let publicAccessShowAiConversation = $state(false);
    let publicAccessHistoricalDays = $state(7);
    let publicAccessMediaHistoricalDays = $state(7);
    let publicAccessRateLimitPerMinute = $state(30);
    let dateFormat = $state('dmy');
    let debugUiEnabled = $state(false);
    let inatPreviewEnabled = $state(false);
    let inatPreviewDirty = $state(false);

    // Notifications
    let discordEnabled = $state(false);
    let discordWebhook = $state('');
    let discordWebhookSaved = $state(false);
    let discordUsername = $state('YA-WAMF');

    let pushoverEnabled = $state(false);
    let pushoverUser = $state('');
    let pushoverUserSaved = $state(false);
    let pushoverToken = $state('');
    let pushoverTokenSaved = $state(false);
    let pushoverPriority = $state(0);

    let telegramEnabled = $state(false);
    let telegramToken = $state('');
    let telegramTokenSaved = $state(false);
    let telegramChatId = $state('');
    let telegramChatIdSaved = $state(false);

    let emailEnabled = $state(false);
    let emailUseOAuth = $state(false);
    let emailOAuthProvider = $state<string | null>(null);
    let emailConnectedEmail = $state<string | null>(null);
    let emailOnlyOnEnd = $state(false);
    let emailSmtpHost = $state('');
    let emailSmtpPort = $state(587);
    let emailSmtpUsername = $state('');
    let emailSmtpPassword = $state('');
    let emailSmtpPasswordSaved = $state(false);
    let emailSmtpUseTls = $state(true);
    let emailFromEmail = $state('');
    let emailToEmail = $state('');
    let emailIncludeSnapshot = $state(true);
    let emailDashboardUrl = $state('');

    let filterWhitelist = $state<string[]>([]);
    let newWhitelistSpecies = $state('');
    let filterConfidence = $state(0.7);
    let filterAudioOnly = $state(false);
    let notifyMode = $state<'silent' | 'final' | 'standard' | 'realtime' | 'custom'>('standard');
    let notifyOnInsert = $state(true);
    let notifyOnUpdate = $state(false);
    let notifyDelayUntilVideo = $state(false);
    let notifyVideoFallbackTimeout = $state(45);
    let notifyCooldownMinutes = $state(0);

    let testingNotification = $state<Record<string, boolean>>({});

    // Accessibility
    let highContrast = $state(false);
    let dyslexiaFont = $state(false);
    let liveAnnouncements = $state(true);
    let aiDiagnosticsEnabled = $state(true);

    // eBird
    let ebirdEnabled = $state(false);
    let ebirdApiKey = $state('');
    let ebirdApiKeySaved = $state(false);
    let ebirdDefaultRadiusKm = $state(25);
    let ebirdDefaultDaysBack = $state(14);
    let ebirdMaxResults = $state(25);
    let ebirdLocale = $state('en');

    // Enrichment sources
    let enrichmentMode = $state<'single' | 'per_enrichment'>('per_enrichment');
    let enrichmentSingleProvider = $state('wikipedia');
    let enrichmentSummarySource = $state('wikipedia');
    let enrichmentTaxonomySource = $state('inaturalist');
    let enrichmentSightingsSource = $state('disabled');
    let enrichmentSeasonalitySource = $state('disabled');
    let enrichmentRaritySource = $state('disabled');
    let enrichmentLinksSources = $state<string[]>(['wikipedia', 'inaturalist']);

    $effect(() => {
        if (highContrast) document.documentElement.classList.add('high-contrast');
        else document.documentElement.classList.remove('high-contrast');
    });

    function addTrustedProxyHost() {
        const host = newTrustedProxyHost.trim();
        if (!host) return;
        if (trustedProxyHostsSuggested) {
            trustedProxyHostsSuggested = false;
        }
        if (!trustedProxyHosts.includes(host)) {
            trustedProxyHosts = [...trustedProxyHosts, host];
        }
        newTrustedProxyHost = '';
    }

    function removeTrustedProxyHost(host: string) {
        if (trustedProxyHostsSuggested) {
            trustedProxyHostsSuggested = false;
        }
        trustedProxyHosts = trustedProxyHosts.filter((item) => item !== host);
    }

    function acceptTrustedProxySuggestions() {
        trustedProxyHostsSuggested = false;
    }

    const effectiveTrustedProxyHosts = $derived.by(() => {
        return trustedProxyHostsSuggested ? ['*'] : trustedProxyHosts;
    });

    $effect(() => {
        if (dyslexiaFont) document.documentElement.classList.add('font-dyslexic');
        else document.documentElement.classList.remove('font-dyslexic');
    });

    $effect(() => {
        if (discordWebhookSaved && discordWebhook) {
            discordWebhookSaved = false;
        }
    });

    $effect(() => {
        if (pushoverUserSaved && pushoverUser) {
            pushoverUserSaved = false;
        }
    });

    $effect(() => {
        if (pushoverTokenSaved && pushoverToken) {
            pushoverTokenSaved = false;
        }
    });

    $effect(() => {
        if (telegramTokenSaved && telegramToken) {
            telegramTokenSaved = false;
        }
    });

    $effect(() => {
        if (telegramChatIdSaved && telegramChatId) {
            telegramChatIdSaved = false;
        }
    });

    $effect(() => {
        if (emailSmtpPasswordSaved && emailSmtpPassword) {
            emailSmtpPasswordSaved = false;
        }
    });

    // Version Info
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    let versionInfo = $state<VersionInfo>({
        version: appVersion,
        base_version: appVersionBase,
        git_hash: __GIT_HASH__,
        branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
    });

    let availableCameras = $state<string[]>([]);
    let camerasLoading = $state(false);

    let loading = $state(true);
    let saving = $state(false);
    let testing = $state(false);
    let testingBirdWeather = $state(false);
    let testingLlm = $state(false);
    let testingBirdNET = $state(false);
    let message = $state<{ type: 'success' | 'error'; text: string } | null>(null);
    let currentTheme: Theme = $state('system');
    let currentLayout: Layout = $state('horizontal');
    let currentFontTheme = $state<import('../stores/theme.svelte').FontTheme>('default');

    const normalizeSecret = (value?: string | null) => value === '***REDACTED***' ? '' : (value || '');

    // Dirty state check
    let isDirty = $derived.by(() => {
        const s = settingsStore.settings;
        if (!s) {
            console.log('isDirty: settingsStore.settings is null');
            return false;
        }

        const checks = [
            { key: 'frigateUrl', val: frigateUrl, store: s.frigate_url },
            { key: 'mqttServer', val: mqttServer, store: s.mqtt_server },
            { key: 'mqttPort', val: mqttPort, store: s.mqtt_port },
            { key: 'mqttAuth', val: mqttAuth, store: s.mqtt_auth },
            { key: 'mqttUsername', val: mqttUsername, store: s.mqtt_username || '' },
            { key: 'mqttPassword', val: mqttPassword, store: s.mqtt_password || '' },
            { key: 'audioTopic', val: audioTopic, store: s.audio_topic || 'birdnet/text' },
            { key: 'audioBufferHours', val: audioBufferHours, store: s.audio_buffer_hours ?? 24 },
            { key: 'audioCorrelationWindowSeconds', val: audioCorrelationWindowSeconds, store: s.audio_correlation_window_seconds ?? 300 },
            { key: 'birdnetEnabled', val: birdnetEnabled, store: s.birdnet_enabled ?? true },
            { key: 'clipsEnabled', val: clipsEnabled, store: s.clips_enabled ?? true },
            { key: 'threshold', val: threshold, store: s.classification_threshold },
            { key: 'trustFrigateSublabel', val: trustFrigateSublabel, store: s.trust_frigate_sublabel ?? true },
            { key: 'displayCommonNames', val: displayCommonNames, store: s.display_common_names ?? true },
            { key: 'scientificNamePrimary', val: scientificNamePrimary, store: s.scientific_name_primary ?? false },
            { key: 'fontTheme', val: currentFontTheme, store: (s.appearance_font_theme ?? 'classic') as any },
            { key: 'autoVideoClassification', val: autoVideoClassification, store: s.auto_video_classification ?? false },
            { key: 'videoClassificationDelay', val: videoClassificationDelay, store: s.video_classification_delay ?? 30 },
            { key: 'videoClassificationMaxRetries', val: videoClassificationMaxRetries, store: s.video_classification_max_retries ?? 3 },
            { key: 'selectedCameras', val: JSON.stringify(selectedCameras), store: JSON.stringify(s.cameras || []) },
            { key: 'retentionDays', val: retentionDays, store: s.retention_days || 0 },
            { key: 'blockedLabels', val: JSON.stringify(blockedLabels), store: JSON.stringify(s.blocked_labels || []) },
            { key: 'cacheEnabled', val: cacheEnabled, store: s.media_cache_enabled ?? true },
            { key: 'cacheSnapshots', val: cacheSnapshots, store: s.media_cache_snapshots ?? true },
            { key: 'cacheClips', val: cacheClips, store: s.media_cache_clips ?? true },
            { key: 'cacheRetentionDays', val: cacheRetentionDays, store: s.media_cache_retention_days ?? 0 },
            { key: 'locationLat', val: locationLat, store: s.location_latitude ?? null },
            { key: 'locationLon', val: locationLon, store: s.location_longitude ?? null },
            { key: 'locationAuto', val: locationAuto, store: s.location_automatic ?? true },
            { key: 'locationTemperatureUnit', val: locationTemperatureUnit, store: s.location_temperature_unit ?? 'celsius' },
            { key: 'birdweatherEnabled', val: birdweatherEnabled, store: s.birdweather_enabled ?? false },
            { key: 'birdweatherStationToken', val: birdweatherStationToken, store: s.birdweather_station_token || '' },
            { key: 'ebirdEnabled', val: ebirdEnabled, store: s.ebird_enabled ?? false },
            { key: 'ebirdApiKey', val: ebirdApiKey, store: normalizeSecret(s.ebird_api_key) },
            { key: 'ebirdDefaultRadiusKm', val: ebirdDefaultRadiusKm, store: s.ebird_default_radius_km ?? 25 },
            { key: 'ebirdDefaultDaysBack', val: ebirdDefaultDaysBack, store: s.ebird_default_days_back ?? 14 },
            { key: 'ebirdMaxResults', val: ebirdMaxResults, store: s.ebird_max_results ?? 25 },
            { key: 'ebirdLocale', val: ebirdLocale, store: s.ebird_locale ?? 'en' },
            { key: 'inaturalistEnabled', val: inaturalistEnabled, store: s.inaturalist_enabled ?? false },
            { key: 'inaturalistClientId', val: inaturalistClientId, store: normalizeSecret(s.inaturalist_client_id) },
            { key: 'inaturalistClientSecret', val: inaturalistClientSecret, store: normalizeSecret(s.inaturalist_client_secret) },
            { key: 'inaturalistDefaultLat', val: inaturalistDefaultLat, store: s.inaturalist_default_latitude ?? null },
            { key: 'inaturalistDefaultLon', val: inaturalistDefaultLon, store: s.inaturalist_default_longitude ?? null },
            { key: 'inaturalistDefaultPlace', val: inaturalistDefaultPlace, store: s.inaturalist_default_place_guess ?? '' },
            { key: 'enrichmentMode', val: enrichmentMode, store: (s.enrichment_mode as typeof enrichmentMode) ?? 'per_enrichment' },
            { key: 'enrichmentSingleProvider', val: enrichmentSingleProvider, store: s.enrichment_single_provider ?? 'wikipedia' },
            { key: 'enrichmentSummarySource', val: enrichmentSummarySource, store: s.enrichment_summary_source ?? 'wikipedia' },
            { key: 'enrichmentTaxonomySource', val: enrichmentTaxonomySource, store: s.enrichment_taxonomy_source ?? 'inaturalist' },
            { key: 'enrichmentSightingsSource', val: enrichmentSightingsSource, store: s.enrichment_sightings_source ?? 'disabled' },
            { key: 'enrichmentSeasonalitySource', val: enrichmentSeasonalitySource, store: s.enrichment_seasonality_source ?? 'disabled' },
            { key: 'enrichmentRaritySource', val: enrichmentRaritySource, store: s.enrichment_rarity_source ?? 'disabled' },
            { key: 'enrichmentLinksSources', val: JSON.stringify(enrichmentLinksSources), store: JSON.stringify(s.enrichment_links_sources || ['wikipedia', 'inaturalist']) },
            { key: 'llmEnabled', val: llmEnabled, store: s.llm_enabled ?? false },
            { key: 'llmProvider', val: llmProvider, store: s.llm_provider ?? 'gemini' },
            { key: 'llmApiKey', val: llmApiKey, store: s.llm_api_key || '' },
            { key: 'llmModel', val: llmModel, store: s.llm_model ?? 'gemini-2.5-flash' },
            { key: 'llmAnalysisPromptTemplate', val: llmAnalysisPromptTemplate, store: s.llm_analysis_prompt_template || '' },
            { key: 'llmConversationPromptTemplate', val: llmConversationPromptTemplate, store: s.llm_conversation_prompt_template || '' },
            { key: 'llmChartPromptTemplate', val: llmChartPromptTemplate, store: s.llm_chart_prompt_template || '' },
            { key: 'cameraAudioMapping', val: JSON.stringify(cameraAudioMapping), store: JSON.stringify(s.camera_audio_mapping || {}) },
            { key: 'minConfidence', val: minConfidence, store: s.classification_min_confidence ?? 0.4 },
            { key: 'telemetryEnabled', val: telemetryEnabled, store: s.telemetry_enabled ?? true },
            { key: 'authEnabled', val: authEnabled, store: s.auth_enabled ?? false },
            { key: 'authUsername', val: authUsername, store: s.auth_username || 'admin' },
            { key: 'authSessionExpiryHours', val: authSessionExpiryHours, store: s.auth_session_expiry_hours ?? 168 },
            { key: 'trustedProxyHosts', val: JSON.stringify(effectiveTrustedProxyHosts), store: JSON.stringify(s.trusted_proxy_hosts || []) },
            { key: 'publicAccessEnabled', val: publicAccessEnabled, store: s.public_access_enabled ?? false },
            { key: 'publicAccessShowCameraNames', val: publicAccessShowCameraNames, store: s.public_access_show_camera_names ?? true },
            { key: 'publicAccessShowAiConversation', val: publicAccessShowAiConversation, store: s.public_access_show_ai_conversation ?? false },
            { key: 'publicAccessHistoricalDays', val: publicAccessHistoricalDays, store: s.public_access_historical_days ?? 7 },
            { key: 'publicAccessMediaHistoricalDays', val: publicAccessMediaHistoricalDays, store: s.public_access_media_historical_days ?? 7 },
            { key: 'publicAccessRateLimitPerMinute', val: publicAccessRateLimitPerMinute, store: s.public_access_rate_limit_per_minute ?? 30 },

            // Notifications
            { key: 'discordEnabled', val: discordEnabled, store: s.notifications_discord_enabled ?? false },
            { key: 'discordWebhook', val: discordWebhook, store: normalizeSecret(s.notifications_discord_webhook_url) },
            { key: 'discordUsername', val: discordUsername, store: s.notifications_discord_username || 'YA-WAMF' },

            { key: 'pushoverEnabled', val: pushoverEnabled, store: s.notifications_pushover_enabled ?? false },
            { key: 'pushoverUser', val: pushoverUser, store: normalizeSecret(s.notifications_pushover_user_key) },
            { key: 'pushoverToken', val: pushoverToken, store: normalizeSecret(s.notifications_pushover_api_token) },
            { key: 'pushoverPriority', val: pushoverPriority, store: s.notifications_pushover_priority ?? 0 },

            { key: 'telegramEnabled', val: telegramEnabled, store: s.notifications_telegram_enabled ?? false },
            { key: 'telegramToken', val: telegramToken, store: normalizeSecret(s.notifications_telegram_bot_token) },
            { key: 'telegramChatId', val: telegramChatId, store: normalizeSecret(s.notifications_telegram_chat_id) },

            { key: 'emailEnabled', val: emailEnabled, store: s.notifications_email_enabled ?? false },
            { key: 'emailUseOAuth', val: emailUseOAuth, store: s.notifications_email_use_oauth ?? false },
            { key: 'emailOAuthProvider', val: emailOAuthProvider || '', store: s.notifications_email_oauth_provider || '' },
            { key: 'emailSmtpHost', val: emailSmtpHost, store: s.notifications_email_smtp_host || '' },
            { key: 'emailSmtpPort', val: emailSmtpPort, store: s.notifications_email_smtp_port ?? 587 },
            { key: 'emailSmtpUsername', val: emailSmtpUsername, store: s.notifications_email_smtp_username || '' },
            { key: 'emailSmtpPassword', val: emailSmtpPassword, store: normalizeSecret(s.notifications_email_smtp_password) },
            { key: 'emailSmtpUseTls', val: emailSmtpUseTls, store: s.notifications_email_smtp_use_tls ?? true },
            { key: 'emailFromEmail', val: emailFromEmail, store: s.notifications_email_from_email || '' },
            { key: 'emailToEmail', val: emailToEmail, store: s.notifications_email_to_email || '' },
            { key: 'emailIncludeSnapshot', val: emailIncludeSnapshot, store: s.notifications_email_include_snapshot ?? true },
            { key: 'emailDashboardUrl', val: emailDashboardUrl, store: s.notifications_email_dashboard_url || '' },

            { key: 'filterWhitelist', val: JSON.stringify(filterWhitelist), store: JSON.stringify(s.notifications_filter_species_whitelist || []) },
            { key: 'filterConfidence', val: filterConfidence, store: s.notifications_filter_min_confidence ?? 0.7 },
            { key: 'filterAudioOnly', val: filterAudioOnly, store: s.notifications_filter_audio_confirmed_only ?? false },
            { key: 'notifyMode', val: notifyMode, store: s.notifications_mode ?? 'standard' },
            { key: 'notifyOnInsert', val: notifyOnInsert, store: s.notifications_notify_on_insert ?? true },
            { key: 'notifyOnUpdate', val: notifyOnUpdate, store: s.notifications_notify_on_update ?? false },
            { key: 'notifyDelayUntilVideo', val: notifyDelayUntilVideo, store: s.notifications_delay_until_video ?? false },
            { key: 'notifyVideoFallbackTimeout', val: notifyVideoFallbackTimeout, store: s.notifications_video_fallback_timeout ?? 45 },

            // Accessibility
            { key: 'highContrast', val: highContrast, store: s.accessibility_high_contrast ?? false },
            { key: 'dyslexiaFont', val: dyslexiaFont, store: s.accessibility_dyslexia_font ?? false },
            { key: 'liveAnnouncements', val: liveAnnouncements, store: s.accessibility_live_announcements ?? true }
        ];

        if (authPassword.length > 0 || authPasswordConfirm.length > 0) {
            return true;
        }

        const dirtyItem = checks.find(c => c.val !== c.store);
        if (dirtyItem) {
            console.log(`Dirty Setting: ${dirtyItem.key}`, { current: dirtyItem.val, saved: dirtyItem.store });
            return true;
        } else {
            // console.log('isDirty: No changes detected');
        }
        return false;
    });

    let classifierStatus = $state<ClassifierStatus | null>(null);
    let downloadingModel = $state(false);

    let wildlifeStatus = $state<WildlifeModelStatus | null>(null);
    let downloadingWildlifeModel = $state(false);

    let maintenanceStats = $state<MaintenanceStats | null>(null);
    let cleaningUp = $state(false);
    let purgingMissingClips = $state(false);
    let purgingMissingSnapshots = $state(false);

    // Media cache state
    let cacheEnabled = $state(true);
    let cacheSnapshots = $state(true);
    let cacheClips = $state(true);
    let cacheRetentionDays = $state(0);
    let cacheStats = $state<CacheStats | null>(null);
    let cleaningCache = $state(false);

    // Backfill state
    let backfillDateRange = $state<'day' | 'week' | 'month' | 'custom'>('week');
    let backfillStartDate = $state('');
    let backfillEndDate = $state('');
    let backfilling = $state(false);
    let backfillResult = $state<BackfillResult | null>(null);
    let backfillJob = $state<BackfillJobStatus | null>(null);
    let backfillTotal = $state(0);
    let weatherBackfilling = $state(false);
    let weatherBackfillResult = $state<WeatherBackfillResult | null>(null);
    let weatherBackfillJob = $state<BackfillJobStatus | null>(null);
    let weatherBackfillTotal = $state(0);
    let backfillPollInterval: ReturnType<typeof setInterval> | null = null;
    let resettingDatabase = $state(false);
    let analyzingUnknowns = $state(false);
    let analysisTotal = $state(0);
    let analysisStatus = $state<{ pending: number; active: number; circuit_open: boolean } | null>(null);
    let analysisPollInterval: any;

    // Tab navigation
    let activeTab = $state('connection');

    $effect(() => {
        currentTheme = themeStore.theme;
        currentLayout = layoutStore.layout;
    });
    $effect(() => {
        currentFontTheme = themeStore.fontTheme;
    });

    onMount(async () => {
        // Guests should never load the Settings view or call /api/settings.
        if (!authStore.showSettings) {
            authStore.requestLogin();
            return;
        }

        // Handle deep linking to tabs
        const hash = window.location.hash.slice(1);
        if (hash && ['connection', 'detection', 'notifications', 'integrations', 'enrichment', 'security', 'data', 'appearance', 'accessibility', 'debug'].includes(hash)) {
            activeTab = hash;
        }

        // Ensure settings store is loaded for dirty checking
        await settingsStore.load();

            await Promise.all([
                loadSettings(),
                loadCameras(),
                loadClassifierStatus(),
                loadWildlifeStatus(),
                loadMaintenanceStats(),
                loadCacheStats(),
                loadTaxonomyStatus(),
                loadVersion(),
                loadAnalysisStatus(), // Check if there's an ongoing job
                loadBackfillStatus()
            ]);
            inatPreviewEnabled = window.localStorage.getItem('inat_preview') === '1';
            inatPreviewDirty = false;
            aiDiagnosticsEnabled = window.localStorage.getItem('ai_diagnostics_enabled') !== '0';

        taxonomyPollInterval = setInterval(loadTaxonomyStatus, 3000);
        
        // If there are pending/active items on load, start polling
        if (analysisStatus && (analysisStatus.pending > 0 || analysisStatus.active > 0)) {
             startAnalysisPolling();
             // We don't know total if we just reloaded, so maybe set total to pending+active
             if (analysisTotal === 0) {
                 analysisTotal = analysisStatus.pending + analysisStatus.active;
             }
        }

        if ((backfillJob && backfillJob.status === 'running') || (weatherBackfillJob && weatherBackfillJob.status === 'running')) {
            startBackfillPolling();
        }
    });

    function handleTabChange(tab: string) {
        console.log('Tab changed to:', tab);
        activeTab = tab;
        window.location.hash = tab;
    }

    function applyInatPreview() {
        window.localStorage.setItem('inat_preview', inatPreviewEnabled ? '1' : '0');
        inatPreviewDirty = false;
        toastStore.success($_('settings.debug.apply_notice'));
    }

    onDestroy(() => {
        if (taxonomyPollInterval) clearInterval(taxonomyPollInterval);
        if (analysisPollInterval) clearInterval(analysisPollInterval);
        if (backfillPollInterval) clearInterval(backfillPollInterval);
    });

    async function loadTaxonomyStatus() {
        try {
            taxonomyStatus = await fetchTaxonomyStatus();
        } catch (e) {
            console.error('Failed to load taxonomy status', e);
        }
    }

    async function loadVersion() {
        try {
            versionInfo = await fetchVersion();
        } catch (e) {
            console.error('Failed to load version info', e);
        }
    }

    async function handleStartTaxonomySync() {
        if (taxonomyStatus?.is_running) return;
        syncingTaxonomy = true;
        try {
            await startTaxonomySync();
            await loadTaxonomyStatus();
        } catch (e: any) {
            alert('Failed to start taxonomy sync: ' + e.message);
        } finally {
            syncingTaxonomy = false;
        }
    }

    async function loadMaintenanceStats() {
        try {
            maintenanceStats = await fetchMaintenanceStats();
        } catch (e) {
            console.error('Failed to load maintenance stats', e);
        }
    }

    async function handleCleanup() {
        cleaningUp = true;
        message = null;
        try {
            const result = await runCleanup();
            if (result.status === 'completed') {
                message = { type: 'success', text: $_('settings.data.cleanup_success', { values: { count: result.deleted_count } }) };
            } else {
                message = { type: 'success', text: result.message || $_('settings.data.cleanup_none') };
            }
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.cleanup_error') };
        } finally {
            cleaningUp = false;
        }
    }

    async function handlePurgeMissingClips() {
        const confirmMsg = $_('settings.data.purge_missing_clips_confirm', {
            default: 'Remove detections without clips? This cannot be undone.'
        });
        if (!confirm(confirmMsg)) return;

        purgingMissingClips = true;
        message = null;
        try {
            const result = await purgeMissingClips();
            const text = result.message
                || `Removed ${result.deleted_count.toLocaleString()} detections without clips (checked ${result.checked.toLocaleString()}).`;
            message = { type: 'success', text };
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.cleanup_error') };
        } finally {
            purgingMissingClips = false;
        }
    }

    async function handlePurgeMissingSnapshots() {
        const confirmMsg = $_('settings.data.purge_missing_snapshots_confirm', {
            default: 'Remove detections without snapshots? This cannot be undone.'
        });
        if (!confirm(confirmMsg)) return;

        purgingMissingSnapshots = true;
        message = null;
        try {
            const result = await purgeMissingSnapshots();
            const text = result.message
                || `Removed ${result.deleted_count.toLocaleString()} detections without snapshots (checked ${result.checked.toLocaleString()}).`;
            message = { type: 'success', text };
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.cleanup_error') };
        } finally {
            purgingMissingSnapshots = false;
        }
    }

    async function handleResetDatabase() {
        console.log('Reset database requested');
        let confirmMsg = 'DANGER: This will delete ALL detections and clear the media cache. This action cannot be undone. Are you sure?';
        try {
            confirmMsg = $_('settings.danger.confirm');
        } catch (e) {
            console.warn('Translation lookup failed, using fallback', e);
        }

        if (!confirm(confirmMsg)) {
            console.log('Reset cancelled by user');
            return;
        }
        
        console.log('Reset confirmed, proceeding...');
        resettingDatabase = true;
        message = null;
        toastStore.show($_('settings.danger.resetting'), 'info');
        try {
            const result = await resetDatabase();
            message = { type: 'success', text: result.message };
            toastStore.success(result.message || $_('settings.danger.reset_button'));
            await Promise.all([loadMaintenanceStats(), loadCacheStats()]);
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.reset_error') };
            toastStore.error(e.message || $_('settings.data.reset_error'));
        } finally {
            resettingDatabase = false;
        }
    }

    async function loadCacheStats() {
        try {
            cacheStats = await fetchCacheStats();
        } catch (e) {
            console.error('Failed to load cache stats', e);
        }
    }

    async function handleCacheCleanup() {
        cleaningCache = true;
        message = null;
        try {
            const result = await runCacheCleanup();
            if (result.status === 'completed') {
                const freed = result.bytes_freed > 1024 * 1024
                    ? `${(result.bytes_freed / (1024 * 1024)).toFixed(1)} MB`
                    : `${(result.bytes_freed / 1024).toFixed(1)} KB`;
                message = { type: 'success', text: $_('settings.data.cache_cleanup_success', { values: { snapshots: result.snapshots_deleted, clips: result.clips_deleted, freed } }) };
            } else {
                message = { type: 'success', text: result.message || $_('settings.data.cleanup_none') };
            }
            await loadCacheStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.cache_cleanup_error') };
        } finally {
            cleaningCache = false;
        }
    }

    async function handleBackfill() {
        backfilling = true;
        message = null;
        backfillResult = null;
        backfillJob = null;
        backfillTotal = 0;
        try {
            const job = await startBackfillJob({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined
            });
            backfillJob = job;
            backfillTotal = job.total || 0;
            startBackfillPolling();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.backfill_error') };
        }
    }

    async function handleWeatherBackfill() {
        weatherBackfilling = true;
        message = null;
        weatherBackfillResult = null;
        weatherBackfillJob = null;
        weatherBackfillTotal = 0;
        try {
            const job = await startWeatherBackfillJob({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined,
                only_missing: true
            });
            weatherBackfillJob = job;
            weatherBackfillTotal = job.total || 0;
            startBackfillPolling();
        } catch (e: any) {
            message = { type: 'error', text: e.message || $_('settings.data.weather_backfill_error') };
        }
    }

    function startBackfillPolling() {
        if (backfillPollInterval) {
            clearInterval(backfillPollInterval);
        }
        loadBackfillStatus();
        backfillPollInterval = setInterval(loadBackfillStatus, 2000);
    }

    async function loadBackfillStatus() {
        try {
            const [detections, weather] = await Promise.all([
                getBackfillStatus('detections'),
                getBackfillStatus('weather')
            ]);

            if (detections) {
                backfillJob = detections;
                backfillResult = {
                    status: detections.status,
                    processed: detections.processed,
                    new_detections: detections.new_detections ?? 0,
                    skipped: detections.skipped,
                    errors: detections.errors,
                    message: detections.message || ''
                };
                backfillTotal = detections.total || 0;
                backfilling = detections.status === 'running';
                if (detections.status === 'completed') {
                    message = { type: 'success', text: detections.message || 'Backfill complete' };
                    await loadMaintenanceStats();
                } else if (detections.status === 'failed') {
                    message = { type: 'error', text: detections.message || 'Backfill failed' };
                }
            }

            if (weather) {
                weatherBackfillJob = weather;
                weatherBackfillResult = {
                    status: weather.status,
                    processed: weather.processed,
                    updated: weather.updated ?? 0,
                    skipped: weather.skipped,
                    errors: weather.errors,
                    message: weather.message || ''
                };
                weatherBackfillTotal = weather.total || 0;
                weatherBackfilling = weather.status === 'running';
                if (weather.status === 'completed') {
                    message = { type: 'success', text: weather.message || 'Weather backfill complete' };
                } else if (weather.status === 'failed') {
                    message = { type: 'error', text: weather.message || 'Weather backfill failed' };
                }
            }

            const detectionsDone = !backfillJob || backfillJob.status !== 'running';
            const weatherDone = !weatherBackfillJob || weatherBackfillJob.status !== 'running';
            if (detectionsDone && weatherDone && backfillPollInterval) {
                clearInterval(backfillPollInterval);
                backfillPollInterval = null;
            }
        } catch (e) {
            console.error('Failed to load backfill status', e);
        }
    }

    async function handleAnalyzeUnknowns() {
        analyzingUnknowns = true;
        message = null;
        try {
            const result = await analyzeUnknowns();
            message = { type: 'success', text: result.message };
            if (result.count > 0) {
                analysisTotal = result.count;
                startAnalysisPolling();
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Analysis failed' };
        } finally {
            analyzingUnknowns = false;
        }
    }

    function startAnalysisPolling() {
        if (analysisPollInterval) clearInterval(analysisPollInterval);
        loadAnalysisStatus();
        analysisPollInterval = setInterval(loadAnalysisStatus, 2000);
    }

    async function loadAnalysisStatus() {
        try {
            const status = await fetchAnalysisStatus();
            analysisStatus = status;
            if (status.pending === 0 && status.active === 0) {
                if (analysisPollInterval) {
                    clearInterval(analysisPollInterval);
                    analysisPollInterval = null;
                }
            }
        } catch (e) {
            console.error('Failed to load analysis status', e);
        }
    }

    async function loadClassifierStatus() {
        try {
            classifierStatus = await fetchClassifierStatus();
        } catch (e) {
            console.error('Failed to load classifier status', e);
        }
    }

    async function loadWildlifeStatus() {
        try {
            wildlifeStatus = await fetchWildlifeModelStatus();
        } catch (e) {
            console.error('Failed to load wildlife status', e);
        }
    }

    async function handleDownloadWildlifeModel() {
        downloadingWildlifeModel = true;
        message = null;
        try {
            const result = await downloadWildlifeModel();
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
                await loadWildlifeStatus();
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to download wildlife model' };
        } finally {
            downloadingWildlifeModel = false;
        }
    }

    async function loadSettings(silent = false) {
        if (!silent) loading = true;
        if (!silent) message = null;
        try {
            const settings = await fetchSettings();
            frigateUrl = settings.frigate_url;
            mqttServer = settings.mqtt_server;
            mqttPort = settings.mqtt_port;
            mqttAuth = settings.mqtt_auth;
            mqttUsername = settings.mqtt_username || '';
            mqttPassword = settings.mqtt_password || '';
            birdnetEnabled = settings.birdnet_enabled ?? true;
            audioTopic = settings.audio_topic || 'birdnet/text';
            cameraAudioMapping = settings.camera_audio_mapping || {};
            if (typeof cameraAudioMapping !== 'object' || Array.isArray(cameraAudioMapping)) {
                cameraAudioMapping = {};
            }
            audioBufferHours = settings.audio_buffer_hours ?? 24;
            audioCorrelationWindowSeconds = settings.audio_correlation_window_seconds ?? 300;
            clipsEnabled = settings.clips_enabled ?? true;
            threshold = settings.classification_threshold;
            minConfidence = settings.classification_min_confidence ?? 0.4;
            trustFrigateSublabel = settings.trust_frigate_sublabel ?? true;
            displayCommonNames = settings.display_common_names ?? true;
            scientificNamePrimary = settings.scientific_name_primary ?? false;
            autoVideoClassification = settings.auto_video_classification ?? false;
            videoClassificationDelay = settings.video_classification_delay ?? 30;
            videoClassificationMaxRetries = settings.video_classification_max_retries ?? 3;
            videoCircuitOpen = settings.video_classification_circuit_open ?? false;
            videoCircuitUntil = settings.video_classification_circuit_until ?? null;
            videoCircuitFailures = settings.video_classification_circuit_failures ?? 0;
            selectedCameras = settings.cameras || [];
            retentionDays = settings.retention_days || 0;
            blockedLabels = settings.blocked_labels || [];
            // Media cache settings
            cacheEnabled = settings.media_cache_enabled ?? true;
            cacheSnapshots = settings.media_cache_snapshots ?? true;
            cacheClips = settings.media_cache_clips ?? true;
            cacheRetentionDays = settings.media_cache_retention_days ?? 0;
            // Location settings
            locationLat = settings.location_latitude ?? null;
            locationLon = settings.location_longitude ?? null;
            locationAuto = settings.location_automatic ?? true;
            locationTemperatureUnit = (settings.location_temperature_unit as 'celsius' | 'fahrenheit') ?? 'celsius';
            // BirdWeather settings
            birdweatherEnabled = settings.birdweather_enabled ?? false;
            birdweatherStationToken = settings.birdweather_station_token ?? '';
            // eBird settings
            ebirdEnabled = settings.ebird_enabled ?? false;
            if (settings.ebird_api_key === '***REDACTED***') {
                ebirdApiKeySaved = true;
                ebirdApiKey = '';
            } else {
                ebirdApiKeySaved = false;
                ebirdApiKey = settings.ebird_api_key || '';
            }
            ebirdDefaultRadiusKm = settings.ebird_default_radius_km ?? 25;
            ebirdDefaultDaysBack = settings.ebird_default_days_back ?? 14;
            ebirdMaxResults = settings.ebird_max_results ?? 25;
            ebirdLocale = settings.ebird_locale ?? 'en';
            // iNaturalist settings
            inaturalistEnabled = settings.inaturalist_enabled ?? false;
            if (settings.inaturalist_client_id === '***REDACTED***') {
                inaturalistClientIdSaved = true;
                inaturalistClientId = '';
            } else {
                inaturalistClientIdSaved = false;
                inaturalistClientId = settings.inaturalist_client_id || '';
            }
            if (settings.inaturalist_client_secret === '***REDACTED***') {
                inaturalistClientSecretSaved = true;
                inaturalistClientSecret = '';
            } else {
                inaturalistClientSecretSaved = false;
                inaturalistClientSecret = settings.inaturalist_client_secret || '';
            }
            inaturalistDefaultLat = settings.inaturalist_default_latitude ?? null;
            inaturalistDefaultLon = settings.inaturalist_default_longitude ?? null;
            inaturalistDefaultPlace = settings.inaturalist_default_place_guess ?? '';
            inaturalistConnectedUser = settings.inaturalist_connected_user ?? null;
            // Enrichment settings
            enrichmentMode = (settings.enrichment_mode as typeof enrichmentMode) ?? 'per_enrichment';
            enrichmentSingleProvider = settings.enrichment_single_provider ?? 'wikipedia';
            enrichmentSummarySource = settings.enrichment_summary_source ?? 'wikipedia';
            enrichmentTaxonomySource = settings.enrichment_taxonomy_source ?? 'inaturalist';
            enrichmentSightingsSource = settings.enrichment_sightings_source ?? 'disabled';
            enrichmentSeasonalitySource = settings.enrichment_seasonality_source ?? 'disabled';
            enrichmentRaritySource = settings.enrichment_rarity_source ?? 'disabled';
            enrichmentLinksSources = settings.enrichment_links_sources || ['wikipedia', 'inaturalist'];
            // LLM settings
            llmEnabled = settings.llm_enabled ?? false;
            llmProvider = settings.llm_provider ?? 'gemini';
            llmApiKey = settings.llm_api_key ?? '';
            llmModel = settings.llm_model ?? 'gemini-2.5-flash';
            llmAnalysisPromptTemplate = settings.llm_analysis_prompt_template ?? '';
            llmConversationPromptTemplate = settings.llm_conversation_prompt_template ?? '';
            llmChartPromptTemplate = settings.llm_chart_prompt_template ?? '';
            // Telemetry
            telemetryEnabled = settings.telemetry_enabled ?? true;
            telemetryInstallationId = settings.telemetry_installation_id;
            telemetryPlatform = settings.telemetry_platform;
            // Authentication + Public access
            authEnabled = settings.auth_enabled ?? false;
            authUsername = settings.auth_username || 'admin';
            authHasPassword = settings.auth_has_password ?? false;
            authPassword = '';
            authPasswordConfirm = '';
            authSessionExpiryHours = settings.auth_session_expiry_hours ?? 168;
            const proxyHosts = settings.trusted_proxy_hosts || [];
            const proxyHostsDefault = proxyHosts.length === 0 || (proxyHosts.length === 1 && proxyHosts[0] === '*');
            trustedProxyHostsSuggested = proxyHostsDefault;
            trustedProxyHosts = proxyHostsDefault ? ['nginx-rp', 'cloudflare-tunnel'] : proxyHosts;
            publicAccessEnabled = settings.public_access_enabled ?? false;
            publicAccessShowCameraNames = settings.public_access_show_camera_names ?? true;
            publicAccessShowAiConversation = settings.public_access_show_ai_conversation ?? false;
            publicAccessHistoricalDays = settings.public_access_historical_days ?? 7;
            publicAccessMediaHistoricalDays = settings.public_access_media_historical_days ?? 7;
            publicAccessRateLimitPerMinute = settings.public_access_rate_limit_per_minute ?? 30;
            if (settings.date_format === 'mdy' || settings.date_format === 'dmy' || settings.date_format === 'ymd') {
                dateFormat = settings.date_format;
            } else {
                dateFormat = 'dmy';
            }
            debugUiEnabled = settings.debug_ui_enabled ?? false;

            // Notifications
            discordEnabled = settings.notifications_discord_enabled ?? false;
            if (settings.notifications_discord_webhook_url === '***REDACTED***') {
                discordWebhookSaved = true;
                discordWebhook = '';
            } else {
                discordWebhookSaved = false;
                discordWebhook = settings.notifications_discord_webhook_url || '';
            }
            discordUsername = settings.notifications_discord_username || 'YA-WAMF';

            pushoverEnabled = settings.notifications_pushover_enabled ?? false;
            if (settings.notifications_pushover_user_key === '***REDACTED***') {
                pushoverUserSaved = true;
                pushoverUser = '';
            } else {
                pushoverUserSaved = false;
                pushoverUser = settings.notifications_pushover_user_key || '';
            }
            if (settings.notifications_pushover_api_token === '***REDACTED***') {
                pushoverTokenSaved = true;
                pushoverToken = '';
            } else {
                pushoverTokenSaved = false;
                pushoverToken = settings.notifications_pushover_api_token || '';
            }
            pushoverPriority = settings.notifications_pushover_priority ?? 0;

            telegramEnabled = settings.notifications_telegram_enabled ?? false;
            if (settings.notifications_telegram_bot_token === '***REDACTED***') {
                telegramTokenSaved = true;
                telegramToken = '';
            } else {
                telegramTokenSaved = false;
                telegramToken = settings.notifications_telegram_bot_token || '';
            }
            if (settings.notifications_telegram_chat_id === '***REDACTED***') {
                telegramChatIdSaved = true;
                telegramChatId = '';
            } else {
                telegramChatIdSaved = false;
                telegramChatId = settings.notifications_telegram_chat_id || '';
            }

            emailEnabled = settings.notifications_email_enabled ?? false;
            emailUseOAuth = settings.notifications_email_use_oauth ?? false;
            emailOAuthProvider = settings.notifications_email_oauth_provider || null;
            emailConnectedEmail = settings.notifications_email_connected_email || null;
            emailOnlyOnEnd = settings.notifications_email_only_on_end ?? false;
            emailSmtpHost = settings.notifications_email_smtp_host || '';
            emailSmtpPort = settings.notifications_email_smtp_port ?? 587;
            emailSmtpUsername = settings.notifications_email_smtp_username || '';
            if (settings.notifications_email_smtp_password === '***REDACTED***') {
                emailSmtpPasswordSaved = true;
                emailSmtpPassword = '';
            } else {
                emailSmtpPasswordSaved = false;
                emailSmtpPassword = settings.notifications_email_smtp_password || '';
            }
            emailSmtpUseTls = settings.notifications_email_smtp_use_tls ?? true;
            emailFromEmail = settings.notifications_email_from_email || '';
            emailToEmail = settings.notifications_email_to_email || '';
            emailIncludeSnapshot = settings.notifications_email_include_snapshot ?? true;
            emailDashboardUrl = settings.notifications_email_dashboard_url || '';

            filterWhitelist = settings.notifications_filter_species_whitelist || [];
            filterConfidence = settings.notifications_filter_min_confidence ?? 0.7;
            filterAudioOnly = settings.notifications_filter_audio_confirmed_only ?? false;
            if (settings.notifications_mode) {
                notifyMode = settings.notifications_mode as typeof notifyMode;
            } else if (!settings.notifications_notify_on_insert && !settings.notifications_notify_on_update) {
                notifyMode = 'silent';
            } else if (settings.notifications_delay_until_video) {
                notifyMode = 'final';
            } else if (settings.notifications_notify_on_insert && settings.notifications_notify_on_update) {
                notifyMode = 'realtime';
            } else {
                notifyMode = 'standard';
            }
            notifyOnInsert = settings.notifications_notify_on_insert ?? true;
            if (settings.notifications_notify_on_update !== undefined) notifyOnUpdate = settings.notifications_notify_on_update;
            if (settings.notifications_delay_until_video !== undefined) notifyDelayUntilVideo = settings.notifications_delay_until_video;
            if (settings.notifications_video_fallback_timeout !== undefined) notifyVideoFallbackTimeout = settings.notifications_video_fallback_timeout;
            if (settings.notifications_notification_cooldown_minutes !== undefined) notifyCooldownMinutes = settings.notifications_notification_cooldown_minutes;

            // Accessibility
            highContrast = settings.accessibility_high_contrast ?? false;
            dyslexiaFont = settings.accessibility_dyslexia_font ?? false;
            liveAnnouncements = settings.accessibility_live_announcements ?? true;

            // Appearance (persisted)
            if (settings.appearance_font_theme) {
                themeStore.setFontTheme(settings.appearance_font_theme as any);
            }
        } catch (e) {
            message = { type: 'error', text: $_('notifications.settings_load_failed') };
        } finally {
            if (!silent) loading = false;
        }
    }

    async function loadCameras() {
        camerasLoading = true;
        try {
            const config = await fetchFrigateConfig();
            if (config && config.cameras) {
                availableCameras = Object.keys(config.cameras);
            }
        } catch (e) {
            console.error('Failed to load cameras from Frigate', e);
            if (selectedCameras.length > 0 && availableCameras.length === 0) {
                 availableCameras = [...selectedCameras];
            }
        } finally {
            camerasLoading = false;
        }
    }

    async function saveSettings() {
        saving = true;
        message = null;
        if (authPassword || authPasswordConfirm) {
            if (authPassword !== authPasswordConfirm) {
                message = { type: 'error', text: 'Passwords do not match' };
                saving = false;
                return;
            }
            if (authPassword.length < 8) {
                message = { type: 'error', text: 'Password must be at least 8 characters' };
                saving = false;
                return;
            }
        }
        try {
            await updateSettings({
                frigate_url: frigateUrl,
                mqtt_server: mqttServer,
                mqtt_port: mqttPort,
                mqtt_auth: mqttAuth,
                mqtt_username: mqttUsername,
                mqtt_password: mqttPassword,
                birdnet_enabled: birdnetEnabled,
                audio_topic: audioTopic,
                camera_audio_mapping: cameraAudioMapping,
                audio_buffer_hours: audioBufferHours,
                audio_correlation_window_seconds: audioCorrelationWindowSeconds,
                clips_enabled: clipsEnabled,
                classification_threshold: threshold,
                classification_min_confidence: minConfidence,
                trust_frigate_sublabel: trustFrigateSublabel,
                display_common_names: displayCommonNames,
                scientific_name_primary: scientificNamePrimary,
                auto_video_classification: autoVideoClassification,
                video_classification_delay: videoClassificationDelay,
                video_classification_max_retries: videoClassificationMaxRetries,
                cameras: selectedCameras,
                retention_days: retentionDays,
                blocked_labels: blockedLabels,
                media_cache_enabled: cacheEnabled,
                media_cache_snapshots: cacheSnapshots,
                media_cache_clips: cacheClips,
                media_cache_retention_days: cacheRetentionDays,
                location_latitude: locationLat,
                location_longitude: locationLon,
                location_automatic: locationAuto,
                location_temperature_unit: locationTemperatureUnit,
                birdweather_enabled: birdweatherEnabled,
                birdweather_station_token: birdweatherStationToken,
                ebird_enabled: ebirdEnabled,
                ebird_api_key: ebirdApiKey,
                ebird_default_radius_km: ebirdDefaultRadiusKm,
                ebird_default_days_back: ebirdDefaultDaysBack,
                ebird_max_results: ebirdMaxResults,
                ebird_locale: ebirdLocale,
                inaturalist_enabled: inaturalistEnabled,
                inaturalist_client_id: inaturalistClientId,
                inaturalist_client_secret: inaturalistClientSecret,
                inaturalist_default_latitude: inaturalistDefaultLat,
                inaturalist_default_longitude: inaturalistDefaultLon,
                inaturalist_default_place_guess: inaturalistDefaultPlace,
                enrichment_mode: enrichmentMode,
                enrichment_single_provider: enrichmentSingleProvider,
                enrichment_summary_source: enrichmentSummarySource,
                enrichment_taxonomy_source: enrichmentTaxonomySource,
                enrichment_sightings_source: enrichmentSightingsSource,
                enrichment_seasonality_source: enrichmentSeasonalitySource,
                enrichment_rarity_source: enrichmentRaritySource,
                enrichment_links_sources: enrichmentLinksSources,
                llm_enabled: llmEnabled,
                llm_provider: llmProvider,
                llm_api_key: llmApiKey,
                llm_model: llmModel,
                llm_analysis_prompt_template: llmAnalysisPromptTemplate,
                llm_conversation_prompt_template: llmConversationPromptTemplate,
                llm_chart_prompt_template: llmChartPromptTemplate,
                telemetry_enabled: telemetryEnabled,
                auth_enabled: authEnabled,
                auth_username: authUsername,
                auth_password: authPassword || undefined,
                auth_session_expiry_hours: authSessionExpiryHours,
                trusted_proxy_hosts: effectiveTrustedProxyHosts,
                public_access_enabled: publicAccessEnabled,
                public_access_show_camera_names: publicAccessShowCameraNames,
                public_access_show_ai_conversation: publicAccessShowAiConversation,
                public_access_historical_days: publicAccessHistoricalDays,
                public_access_media_historical_days: publicAccessMediaHistoricalDays,
                public_access_rate_limit_per_minute: publicAccessRateLimitPerMinute,
                date_format: dateFormat,

                // Notifications
                notifications_discord_enabled: discordEnabled,
                notifications_discord_webhook_url: discordWebhook,
                notifications_discord_username: discordUsername,

                notifications_pushover_enabled: pushoverEnabled,
                notifications_pushover_user_key: pushoverUser,
                notifications_pushover_api_token: pushoverToken,
                notifications_pushover_priority: pushoverPriority,

                notifications_telegram_enabled: telegramEnabled,
                notifications_telegram_bot_token: telegramToken,
                notifications_telegram_chat_id: telegramChatId,

                notifications_email_enabled: emailEnabled,
                notifications_email_only_on_end: emailOnlyOnEnd,
                notifications_email_use_oauth: emailUseOAuth,
                notifications_email_oauth_provider: emailOAuthProvider,
                notifications_email_smtp_host: emailSmtpHost,
                notifications_email_smtp_port: emailSmtpPort,
                notifications_email_smtp_username: emailSmtpUsername,
                notifications_email_smtp_password: emailSmtpPassword,
                notifications_email_smtp_use_tls: emailSmtpUseTls,
                notifications_email_from_email: emailFromEmail,
                notifications_email_to_email: emailToEmail,
                notifications_email_include_snapshot: emailIncludeSnapshot,
                notifications_email_dashboard_url: emailDashboardUrl,

                notifications_filter_species_whitelist: filterWhitelist,
                notifications_filter_min_confidence: filterConfidence,
                notifications_filter_audio_confirmed_only: filterAudioOnly,
                notifications_mode: notifyMode,
                notifications_notify_on_insert: notifyOnInsert,
                notifications_notify_on_update: notifyOnUpdate,
                notifications_delay_until_video: notifyDelayUntilVideo,
                notifications_video_fallback_timeout: notifyVideoFallbackTimeout,
                notifications_notification_cooldown_minutes: notifyCooldownMinutes,

                // Accessibility
                accessibility_high_contrast: highContrast,
                accessibility_dyslexia_font: dyslexiaFont,
                accessibility_live_announcements: liveAnnouncements,

                // Appearance
                appearance_font_theme: currentFontTheme
            });
            // Update store
            await settingsStore.load();
            // Public access flags are also used outside Settings (guest gating, etc.)
            await authStore.loadStatus();
            // Sync local state to handle server-side normalization (e.g. stripped slashes)
            await loadSettings(true);
            message = { type: 'success', text: $_('notifications.settings_saved') };
            await Promise.all([loadMaintenanceStats(), loadCacheStats()]);
        } catch (e) {
            message = { type: 'error', text: 'Failed to save settings' };
        } finally {
            saving = false;
        }
    }

    async function testConnection() {
        testing = true;
        message = null;
        try {
            const result = await testFrigateConnection();
            if (result.status === 'ok') {
                message = { type: 'success', text: `Connected to Frigate v${result.version} at ${result.frigate_url}` };
            } else {
                message = { type: 'error', text: 'Frigate returned unexpected status' };
            }
        } catch (e: any) {
            const errorMsg = e.message || 'Failed to connect to Frigate';
            message = { type: 'error', text: errorMsg };
        } finally {
            testing = false;
        }
    }

    async function handleTestBirdWeather() {
        testingBirdWeather = true;
        message = null;
        try {
            const result = await testBirdWeather(birdweatherStationToken);
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test BirdWeather' };
        } finally {
            testingBirdWeather = false;
        }
    }

    async function handleTestBirdNET() {
        testingBirdNET = true;
        message = null;
        try {
            // Test generic MQTT first
            const mqttResult = await testMQTTPublish();
            if (mqttResult.status !== 'ok') {
                throw new Error(mqttResult.message);
            }

            // Then test BirdNET specific pipeline
            const result = await testBirdNET();
            if (result.status === 'ok') {
                message = { type: 'success', text: "MQTT Pipeline Verified: Test message sent to 'yawamf/test' and mock bird injected." };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test MQTT Pipeline' };
        } finally {
            testingBirdNET = false;
        }
    }

    async function handleTestLlm() {
        testingLlm = true;
        message = null;
        try {
            const result = await testLlm({
                llm_enabled: llmEnabled,
                llm_provider: llmProvider,
                llm_model: llmModel,
                llm_api_key: llmApiKey
            });
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test AI integration' };
        } finally {
            testingLlm = false;
        }
    }

    function toggleCamera(camera: string) {
        if (selectedCameras.includes(camera)) {
            selectedCameras = selectedCameras.filter(c => c !== camera);
        } else {
            selectedCameras = [...selectedCameras, camera];
        }
    }

    function setTheme(t: Theme) {
        themeStore.setTheme(t);
    }

    function setFontTheme(font: import('../stores/theme.svelte').FontTheme) {
        themeStore.setFontTheme(font);
    }

    function setLayout(l: Layout) {
        layoutStore.setLayout(l);
    }

    function setLanguage(lang: string) {
        locale.set(lang);
        localStorage.setItem('preferred-language', lang);
    }

    function addBlockedLabel() {
        const label = newBlockedLabel.trim();
        if (label && !blockedLabels.includes(label)) {
            blockedLabels = [...blockedLabels, label];
            newBlockedLabel = '';
        }
    }

    function removeBlockedLabel(label: string) {
        blockedLabels = blockedLabels.filter(l => l !== label);
    }

    async function handleTestNotification(platform: string) {
        testingNotification[platform] = true;
        message = null;

        const credentials: any = {};
        if (platform === 'discord') {
            credentials.webhook_url = discordWebhook;
        } else if (platform === 'pushover') {
            credentials.user_key = pushoverUser;
            credentials.api_token = pushoverToken;
        } else if (platform === 'telegram') {
            credentials.bot_token = telegramToken;
            credentials.chat_id = telegramChatId;
        }

        try {
            const result = await testNotification(platform, credentials);
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || `Failed to test ${platform}` };
        } finally {
            testingNotification[platform] = false;
        }
    }

    function addWhitelistSpecies() {
        const species = newWhitelistSpecies.trim();
        if (species && !filterWhitelist.includes(species)) {
            filterWhitelist = [...filterWhitelist, species];
            newWhitelistSpecies = '';
        }
    }

    function removeWhitelistSpecies(species: string) {
        filterWhitelist = filterWhitelist.filter(s => s !== species);
    }

    // Wrapper functions for notification testing to match component API
    async function sendTestDiscord() {
        await handleTestNotification('discord');
    }

    async function sendTestPushover() {
        await handleTestNotification('pushover');
    }

    async function sendTestTelegram() {
        await handleTestNotification('telegram');
    }
</script>

<div class="max-w-4xl mx-auto space-y-8 pb-20">
    <!-- Header -->
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-3xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.title')}</h2>
            <p class="text-sm text-slate-500 dark:text-slate-400 font-medium">{$_('settings.subtitle')}</p>
        </div>
        <button
            onclick={() => loadSettings()}
            disabled={loading}
            class="btn btn-secondary px-4 py-2 text-sm font-bold"
        >
            <svg class="w-4 h-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {$_('common.refresh')}
        </button>
    </div>

    <!-- Status Messages -->
    {#if message}
        <div class="p-4 rounded-2xl animate-in slide-in-from-top-2 {message.type === 'success'
            ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
            : 'bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20'}">
            <div class="flex items-center gap-3">
                {#if message.type === 'success'}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>
                {:else}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                {/if}
                <span class="font-bold text-sm">{message.text}</span>
            </div>
        </div>
    {/if}

    {#if loading}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            {#each [1, 2, 3, 4] as _}
                <div class="h-48 bg-slate-100 dark:bg-slate-800/50 rounded-3xl animate-pulse border border-slate-200 dark:border-slate-700/50"></div>
            {/each}
        </div>
    {:else}
        <!-- Tab Navigation -->
        <SettingsTabs {activeTab} {debugUiEnabled} ontabchange={handleTabChange} />

        <div class="space-y-6">
            <!-- Connection Tab -->
            {#if activeTab === 'connection'}
                <ConnectionSettings
                    bind:frigateUrl
                    bind:mqttServer
                    bind:mqttPort
                    bind:mqttAuth
                    bind:mqttUsername
                    bind:mqttPassword
                    bind:selectedCameras
                    bind:clipsEnabled
                    bind:telemetryEnabled
                    {availableCameras}
                    {camerasLoading}
                    {testing}
                    {telemetryInstallationId}
                    {telemetryPlatform}
                    {versionInfo}
                    {testConnection}
                    {loadCameras}
                    {handleTestBirdNET}
                    {toggleCamera}
                    bind:testingBirdNET
                />
            {/if}

            <!-- Detection Tab -->
            {#if activeTab === 'detection'}
                <DetectionSettings
                    bind:threshold
                    bind:minConfidence
                    bind:trustFrigateSublabel
                    bind:displayCommonNames
                    bind:scientificNamePrimary
                    bind:autoVideoClassification
                    bind:videoClassificationDelay
                    bind:videoClassificationMaxRetries
                    bind:blockedLabels
                    bind:newBlockedLabel
                    {videoCircuitOpen}
                    {videoCircuitUntil}
                    {videoCircuitFailures}
                    {addBlockedLabel}
                    {removeBlockedLabel}
                />
            {/if}

            <!-- Notifications Tab -->
            {#if activeTab === 'notifications'}
                <NotificationSettings
                    bind:notifyMinConfidence={filterConfidence}
                    bind:notifyAudioOnly={filterAudioOnly}
                    bind:notifySpeciesWhitelist={filterWhitelist}
                    bind:newSpecies={newWhitelistSpecies}
                    bind:notifyMode
                    bind:notifyOnInsert
                    bind:notifyOnUpdate
                    bind:notifyDelayUntilVideo
                    bind:notifyVideoFallbackTimeout
                    bind:notifyCooldownMinutes
                    bind:discordEnabled
                    bind:discordWebhook
                    bind:discordWebhookSaved
                    bind:discordBotName={discordUsername}
                    bind:pushoverEnabled
                    bind:pushoverUserKey={pushoverUser}
                    bind:pushoverUserSaved
                    bind:pushoverApiToken={pushoverToken}
                    bind:pushoverTokenSaved
                    bind:pushoverPriority
                    bind:telegramEnabled
                    bind:telegramBotToken={telegramToken}
                    bind:telegramTokenSaved
                    bind:telegramChatId
                    bind:telegramChatIdSaved
                    bind:emailEnabled
                    bind:emailUseOAuth
                    bind:emailConnectedEmail
                    bind:emailOAuthProvider
                    bind:emailOnlyOnEnd
                    bind:emailSmtpHost
                    bind:emailSmtpPort
                    bind:emailSmtpUseTls
                    bind:emailSmtpUsername
                    bind:emailSmtpPassword
                    bind:emailSmtpPasswordSaved
                    bind:emailFromEmail
                    bind:emailToEmail
                    bind:emailIncludeSnapshot
                    bind:emailDashboardUrl
                    bind:testingNotification
                    addSpeciesToWhitelist={addWhitelistSpecies}
                    removeSpeciesFromWhitelist={removeWhitelistSpecies}
                    {sendTestDiscord}
                    {sendTestPushover}
                    {sendTestTelegram}
                    {sendTestEmail}
                    {initiateGmailOAuth}
                    {initiateOutlookOAuth}
                    {disconnectEmailOAuth}
                />
            {/if}

            <!-- Integrations Tab -->
            {#if activeTab === 'integrations'}
                <IntegrationSettings
                    bind:birdnetEnabled
                    bind:audioTopic
                    bind:audioBufferHours
                    bind:audioCorrelationWindowSeconds
                    bind:cameraAudioMapping
                    bind:birdweatherEnabled
                    bind:birdweatherStationToken
                    bind:ebirdEnabled
                    bind:ebirdApiKey
                    bind:ebirdApiKeySaved
                    bind:ebirdDefaultRadiusKm
                    bind:ebirdDefaultDaysBack
                    bind:ebirdMaxResults
                    bind:ebirdLocale
                    bind:inaturalistEnabled
                    bind:inaturalistClientId
                    bind:inaturalistClientSecret
                    bind:inaturalistClientIdSaved
                    bind:inaturalistClientSecretSaved
                    bind:inaturalistDefaultLat
                    bind:inaturalistDefaultLon
                    bind:inaturalistDefaultPlace
                    bind:inaturalistConnectedUser
                    bind:llmEnabled
                    bind:llmProvider
                    bind:llmApiKey
                    bind:llmModel
                    bind:locationLat
                    bind:locationLon
                    bind:locationAuto
                    bind:locationTemperatureUnit
                    {availableCameras}
                    {availableModels}
                    {testingBirdWeather}
                    {testingLlm}
                    {handleTestBirdNET}
                    {handleTestBirdWeather}
                    {handleTestLlm}
                    {initiateInaturalistOAuth}
                    {disconnectInaturalistOAuth}
                    {exportEbirdCsv}
                    refreshInaturalistStatus={async () => {
                        await settingsStore.load();
                        await loadSettings(true);
                    }}
                    bind:testingBirdNET
                />
            {/if}

            <!-- Enrichment Tab -->
            {#if activeTab === 'enrichment'}
                <EnrichmentSettings
                    enrichmentMode={enrichmentMode}
                    enrichmentSingleProvider={enrichmentSingleProvider}
                    enrichmentSummarySource={enrichmentSummarySource}
                    enrichmentTaxonomySource={enrichmentTaxonomySource}
                    enrichmentSightingsSource={enrichmentSightingsSource}
                    enrichmentSeasonalitySource={enrichmentSeasonalitySource}
                    enrichmentRaritySource={enrichmentRaritySource}
                    enrichmentLinksSources={enrichmentLinksSources}
                />
            {/if}

            <!-- Security Tab -->
            {#if activeTab === 'security'}
                {#if authStore.httpsWarning}
                    <div class="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">
                        <div class="flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <span><strong>Security Warning:</strong> Authentication is enabled over HTTP. Your credentials may be exposed. Use HTTPS in production.</span>
                        </div>
                    </div>
                {/if}
                <AuthenticationSettings
                    bind:authEnabled
                    bind:authUsername
                    bind:authHasPassword
                    bind:authPassword
                    bind:authPasswordConfirm
                    bind:authSessionExpiryHours
                    bind:trustedProxyHosts
                    bind:trustedProxyHostsSuggested
                    bind:newTrustedProxyHost
                    bind:publicAccessEnabled
                    bind:publicAccessShowCameraNames
                    bind:publicAccessShowAiConversation
                    bind:publicAccessHistoricalDays
                    bind:publicAccessMediaHistoricalDays
                    bind:publicAccessRateLimitPerMinute
                    addTrustedProxyHost={addTrustedProxyHost}
                    removeTrustedProxyHost={removeTrustedProxyHost}
                    acceptTrustedProxySuggestions={acceptTrustedProxySuggestions}
                />
            {/if}

            <!-- Data Tab -->
            {#if activeTab === 'data'}
                <DataSettings
                    bind:retentionDays
                    bind:cacheEnabled
                    bind:cacheSnapshots
                    bind:cacheClips
                    bind:cacheRetentionDays
                    bind:backfillDateRange
                    bind:backfillStartDate
                    bind:backfillEndDate
                    {maintenanceStats}
                    {cacheStats}
                    {cleaningUp}
                    {purgingMissingClips}
                    {purgingMissingSnapshots}
                    {cleaningCache}
                    {backfilling}
                    {backfillResult}
                    {backfillTotal}
                    {weatherBackfilling}
                    {weatherBackfillResult}
                    {weatherBackfillTotal}
                    {taxonomyStatus}
                    {syncingTaxonomy}
                    {resettingDatabase}
                    {analyzingUnknowns}
                    {analysisStatus}
                    {analysisTotal}
                    {handleCleanup}
                    {handlePurgeMissingClips}
                    {handlePurgeMissingSnapshots}
                    {handleCacheCleanup}
                    {handleStartTaxonomySync}
                    {handleBackfill}
                    {handleWeatherBackfill}
                    {handleAnalyzeUnknowns}
                    {handleResetDatabase}
                />
            {/if}

            <!-- Appearance Tab -->
            {#if activeTab === 'appearance'}
                <AppearanceSettings
                    {currentTheme}
                    {currentLayout}
                    currentLocale={$locale || 'en'}
                    currentDateFormat={dateFormat}
                    {setTheme}
                    {currentFontTheme}
                    {setFontTheme}
                    {setLayout}
                    {setLanguage}
                    setDateFormat={(value) => (dateFormat = value)}
                />
            {/if}

            <!-- Accessibility Tab -->
            {#if activeTab === 'accessibility'}
                <AccessibilitySettings
                    bind:highContrast
                    bind:dyslexiaFont
                    bind:liveAnnouncements
                />
            {/if}

            {#if activeTab === 'debug'}
                <div class="space-y-6">
                    <section class="card-base p-8">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-slate-900/5 dark:bg-slate-100/10 flex items-center justify-center text-slate-600 dark:text-slate-300">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 3v2.25M14.25 3v2.25M4.5 7.5h15M6 7.5a6 6 0 0 0 12 0m-9 6h6m-3 0v6" /></svg>
                            </div>
                            <div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.debug.title')}</h3>
                                <p class="text-xs text-slate-500">{$_('settings.debug.subtitle')}</p>
                            </div>
                        </div>

                        <div class="space-y-4">
                            <div class="flex items-center justify-between gap-4 rounded-2xl border border-slate-200/70 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 px-4 py-3">
                                <div>
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.debug.ai_diagnostics', { default: 'AI Diagnostics Clipboard' })}</span>
                                    <span class="block text-[10px] font-bold text-slate-500 mt-1">{$_('settings.debug.ai_diagnostics_desc', { default: 'Show a top-of-modal copy button that captures full AI diagnostics and prompts.' })}</span>
                                </div>
                                <button
                                    role="switch"
                                    aria-checked={aiDiagnosticsEnabled}
                                    onclick={() => {
                                        aiDiagnosticsEnabled = !aiDiagnosticsEnabled;
                                        window.localStorage.setItem('ai_diagnostics_enabled', aiDiagnosticsEnabled ? '1' : '0');
                                        // Storage events don't fire in the same tab; broadcast so open modals update immediately.
                                        window.dispatchEvent(new CustomEvent('ai-diagnostics-enabled-changed', { detail: { enabled: aiDiagnosticsEnabled } }));
                                    }}
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            aiDiagnosticsEnabled = !aiDiagnosticsEnabled;
                                            window.localStorage.setItem('ai_diagnostics_enabled', aiDiagnosticsEnabled ? '1' : '0');
                                            window.dispatchEvent(new CustomEvent('ai-diagnostics-enabled-changed', { detail: { enabled: aiDiagnosticsEnabled } }));
                                        }
                                    }}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {aiDiagnosticsEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="sr-only">{$_('settings.debug.ai_diagnostics', { default: 'AI Diagnostics Clipboard' })}</span>
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {aiDiagnosticsEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>
                            <div class="flex items-center justify-between gap-4 rounded-2xl border border-slate-200/70 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 px-4 py-3">
                                <div>
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.debug.inat_preview')}</span>
                                    <span class="block text-[10px] font-bold text-slate-500 mt-1">{$_('settings.debug.inat_preview_desc')}</span>
                                </div>
                                <button
                                    role="switch"
                                    aria-checked={inatPreviewEnabled}
                                    onclick={() => {
                                        inatPreviewEnabled = !inatPreviewEnabled;
                                        inatPreviewDirty = true;
                                    }}
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            inatPreviewEnabled = !inatPreviewEnabled;
                                            inatPreviewDirty = true;
                                        }
                                    }}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {inatPreviewEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="sr-only">{$_('settings.debug.inat_preview')}</span>
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {inatPreviewEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>
                            <div class="flex items-center justify-between text-[10px] font-bold">
                                <span class={inatPreviewDirty ? 'text-amber-600' : 'text-emerald-600/80'}>
                                    {inatPreviewDirty ? $_('settings.debug.apply_pending') : $_('settings.debug.apply_applied')}
                                </span>
                                <button
                                    type="button"
                                    class="px-3 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50 disabled:cursor-not-allowed"
                                    disabled={!inatPreviewDirty}
                                    onclick={applyInatPreview}
                                >
                                    {$_('settings.debug.apply_button')}
                                </button>
                            </div>
                            <div class="text-[10px] font-bold text-slate-500">
                                {$_('settings.debug.inat_preview_hint')}
                            </div>
                        </div>
                    </section>

                    <section class="card-base p-8">
                        <div class="flex items-center gap-3 mb-6">
                            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 4h10M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>
                            </div>
                            <div>
                                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">
                                    {$_('settings.debug.llm_prompts_title', { default: 'LLM Prompt Templates' })}
                                </h3>
                                <p class="text-xs text-slate-500">
                                    {$_('settings.debug.llm_prompts_subtitle', { default: 'Customize the Markdown structure and tone for AI analysis and conversations.' })}
                                </p>
                            </div>
                        </div>

                        <div class="space-y-6">
                            <div class="flex flex-col gap-4 md:flex-row md:items-end">
                                <div class="flex-1">
                                    <label for="llm-prompt-style" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                                        {$_('settings.debug.llm_prompt_style_label', { default: 'Prompt Style' })}
                                    </label>
                                    <select
                                        id="llm-prompt-style"
                                        bind:value={llmPromptStyle}
                                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-semibold text-slate-900 dark:text-slate-100"
                                    >
                                        <option value="classic">{$_('settings.debug.llm_prompt_style_classic', { default: 'Classic' })}</option>
                                        <option value="field">{$_('settings.debug.llm_prompt_style_field', { default: 'Field Notes' })}</option>
                                    </select>
                                    <p class="mt-2 text-[10px] text-slate-500">
                                        {$_('settings.debug.llm_prompt_style_help', { default: 'Applies localized defaults for your current language.' })}
                                    </p>
                                </div>
                                <div class="flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        onclick={() => applyPromptTemplates(llmPromptStyle as keyof typeof promptTemplates)}
                                        class="px-4 py-2 rounded-full border border-teal-200/70 dark:border-teal-700/60 text-[10px] font-black uppercase tracking-widest text-teal-700 dark:text-teal-200 hover:bg-teal-50 dark:hover:bg-teal-900/20 transition"
                                    >
                                        {$_('settings.debug.llm_prompt_apply_style', { default: 'Apply Style' })}
                                    </button>
                                    <button
                                        type="button"
                                        onclick={resetPromptTemplates}
                                        class="px-4 py-2 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                                    >
                                        {$_('settings.debug.llm_prompt_reset_defaults', { default: 'Reset Defaults' })}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label for="llm-prompt-analysis" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                                    {$_('settings.debug.llm_prompt_analysis', { default: 'Detection Analysis Prompt' })}
                                </label>
                                <textarea
                                    id="llm-prompt-analysis"
                                    rows="10"
                                    bind:value={llmAnalysisPromptTemplate}
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-mono text-slate-900 dark:text-slate-100 leading-relaxed"
                                ></textarea>
                                <p class="mt-2 text-[10px] text-slate-500">
                                    {$_('settings.debug.llm_prompt_analysis_hint', { default: 'Tokens: {species}, {time}, {weather_str}, {frame_note}, {language_note}' })}
                                </p>
                            </div>

                            <div>
                                <label for="llm-prompt-conversation" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                                    {$_('settings.debug.llm_prompt_conversation', { default: 'Conversation Prompt' })}
                                </label>
                                <textarea
                                    id="llm-prompt-conversation"
                                    rows="10"
                                    bind:value={llmConversationPromptTemplate}
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-mono text-slate-900 dark:text-slate-100 leading-relaxed"
                                ></textarea>
                                <p class="mt-2 text-[10px] text-slate-500">
                                    {$_('settings.debug.llm_prompt_conversation_hint', { default: 'Tokens: {species}, {analysis}, {history}, {question}, {language_note}' })}
                                </p>
                            </div>

                            <div>
                                <label for="llm-prompt-chart" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                                    {$_('settings.debug.llm_prompt_chart', { default: 'Chart Analysis Prompt' })}
                                </label>
                                <textarea
                                    id="llm-prompt-chart"
                                    rows="10"
                                    bind:value={llmChartPromptTemplate}
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-mono text-slate-900 dark:text-slate-100 leading-relaxed"
                                ></textarea>
                                <p class="mt-2 text-[10px] text-slate-500">
                                    {$_('settings.debug.llm_prompt_chart_hint', { default: 'Tokens: {timeframe}, {total_count}, {series}, {weather_notes}, {sun_notes}, {notes}, {language_note}' })}
                                </p>
                            </div>
                        </div>
                    </section>
                </div>
            {/if}
        </div>

        <!-- Save Button (Sticky Footer) -->
        {#if isDirty}
            <div class="fixed bottom-0 left-0 right-0 bg-white/95 dark:bg-slate-900/95 backdrop-blur-lg border-t border-slate-200 dark:border-slate-700 shadow-2xl z-50 animate-in slide-in-from-bottom-4">
                <div class="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
                    <div class="flex items-center gap-3 text-slate-600 dark:text-slate-400">
                        <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                        <span class="text-sm font-bold">{$_('common.unsaved_changes')}</span>
                    </div>
                    <button
                        onclick={saveSettings}
                        disabled={saving}
                        class="px-8 py-3 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-600 hover:to-emerald-600
                               text-white font-black text-sm uppercase tracking-widest rounded-2xl shadow-lg
                               shadow-teal-500/30 transition-all disabled:opacity-50"
                    >
                        {saving ? $_('common.saving') : $_('common.apply_settings')}
                    </button>
                </div>
            </div>
        {/if}
    {/if}
</div>
