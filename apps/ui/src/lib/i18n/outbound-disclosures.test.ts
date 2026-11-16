import { describe, expect, it } from 'vitest';
import de from './locales/de/about.json';
import en from './locales/en/about.json';
import es from './locales/es/about.json';
import fr from './locales/fr/about.json';
import it_ from './locales/it/about.json';
import ja from './locales/ja/about.json';
import pt from './locales/pt/about.json';
import ru from './locales/ru/about.json';
import zh from './locales/zh/about.json';

/**
 * What each row of "What leaves your network" has to disclose, in every language.
 *
 * The rows are claims about what is sent and to whom. A translation that drops a provider, the
 * coordinates or the installation ID is a privacy list that says less than the truth in that
 * language, and nothing else would notice: the key is still there and still has text. So each
 * disclosure is asserted by the word that carries it, per locale. A name (GitHub, placehold.co) is
 * the same everywhere; a concept has the term each translation uses for it.
 */
type Locale = 'en' | 'de' | 'es' | 'fr' | 'it' | 'ja' | 'pt' | 'ru' | 'zh';

const OUTBOUND: Record<Locale, Record<string, string>> = {
    en: en.outbound, de: de.outbound, es: es.outbound, fr: fr.outbound, it: it_.outbound,
    ja: ja.outbound, pt: pt.outbound, ru: ru.outbound, zh: zh.outbound
};
const LOCALES = Object.keys(OUTBOUND) as Locale[];

/** A concept and the word for it in each translation, matched without regard to case. */
const TERMS = {
    coordinates: { en: 'coordinates', de: 'Koordinaten', es: 'coordenadas', fr: 'coordonnées', it: 'coordinate', ja: '座標', pt: 'coordenadas', ru: 'координат', zh: '坐标' },
    installationId: { en: 'installation ID', de: 'Installations-ID', es: 'ID de instalación', fr: 'identifiant d’installation', it: 'ID di installazione', ja: 'インストール ID', pt: 'ID de instalação', ru: 'идентификатор установки', zh: '安装 ID' },
    diagnostic: { en: 'diagnostic', de: 'Diagnose', es: 'diagnóstico', fr: 'diagnostic', it: 'diagnostic', ja: '診断', pt: 'diagnóstico', ru: 'диагностическ', zh: '诊断' },
    configuration: { en: 'configuration', de: 'Konfiguration', es: 'configuración', fr: 'configuration', it: 'configurazione', ja: '設定', pt: 'configuração', ru: 'настройк', zh: '配置' },
    camera: { en: 'camera', de: 'Kamera', es: 'cámara', fr: 'caméra', it: 'telecamera', ja: 'カメラ', pt: 'câmera', ru: 'камер', zh: '摄像头' },
    link: { en: 'link', de: 'Link', es: 'enlace', fr: 'lien', it: 'link', ja: 'リンク', pt: 'link', ru: 'ссылк', zh: '链接' },
    address: { en: 'address', de: 'Adresse', es: 'dirección', fr: 'adresse', it: 'indirizzo', ja: 'アドレス', pt: 'endereço', ru: 'адрес', zh: '地址' },
    weather: { en: 'weather', de: 'Wetter', es: 'tiempo', fr: 'météo', it: 'meteo', ja: '天気', pt: 'tempo', ru: 'погод', zh: '天气' },
    photo: { en: 'photo', de: 'Foto', es: 'foto', fr: 'photo', it: 'foto', ja: '写真', pt: 'foto', ru: 'фото', zh: '照片' },
    confidence: { en: 'confidence', de: 'Konfidenz', es: 'confianza', fr: 'confiance', it: 'confidenza', ja: '信頼度', pt: 'confiança', ru: 'уверенность', zh: '置信度' },
    conversation: { en: 'conversation', de: 'Gespräch', es: 'conversación', fr: 'conversation', it: 'conversazione', ja: '会話', pt: 'conversa', ru: 'переписк', zh: '对话' },
    saved: { en: 'saved', de: 'gespeichert', es: 'guardad', fr: 'enregistré', it: 'salvat', ja: '保存済み', pt: 'salv', ru: 'сохранённ', zh: '已保存' },
    email: { en: 'email', de: 'E-Mail', es: 'correo', fr: 'e-mail', it: 'e-mail', ja: 'メール', pt: 'e-mail', ru: 'почт', zh: '邮件' },
    token: { en: 'token', de: 'Token', es: 'token', fr: 'jeton', it: 'token', ja: 'トークン', pt: 'token', ru: 'токен', zh: '令牌' },
    key: { en: 'key', de: 'Schlüssel', es: 'clave', fr: 'clé', it: 'chiave', ja: '鍵', pt: 'chave', ru: 'ключ', zh: '密钥' },
    apiKey: { en: 'API key', de: 'API-Schlüssel', es: 'clave de API', fr: 'clé d’API', it: 'chiave API', ja: 'API キー', pt: 'chave de API', ru: 'ключ API', zh: 'API 密钥' },
    captureId: { en: 'ID', de: 'ID', es: 'ID', fr: 'identifiant', it: 'ID', ja: 'ID', pt: 'ID', ru: 'идентификатор', zh: 'ID' },
    account: { en: 'account', de: 'Konto', es: 'cuenta', fr: 'compte', it: 'account', ja: 'アカウント', pt: 'conta', ru: 'учётной записи', zh: '账户' },
    automatic: { en: 'automatic', de: 'automatisch', es: 'automática', fr: 'automatique', it: 'automatico', ja: '自動', pt: 'automática', ru: 'автоматическ', zh: '自动' }
} satisfies Record<string, Record<Locale, string>>;

type Disclosure = keyof typeof TERMS | { name: string };
const named = (...names: string[]): Disclosure[] => names.map((name) => ({ name }));

/** Row by row: what its description must say. */
const REQUIRED: Record<string, Disclosure[]> = {
    weather_desc: ['coordinates'],
    places_desc: ['coordinates'],
    ebird_desc: ['coordinates', 'apiKey'],
    birdweather_desc: ['coordinates', 'token', 'confidence'],
    inat_local_desc: ['coordinates'],
    geolocate_desc: named('IP'),
    llm_desc: ['photo', 'weather', 'conversation', 'key'],
    notify_desc: ['camera', 'confidence', 'link', 'photo', 'weather', ...named('Discord', 'Telegram', 'Pushover')],
    garden_notify_desc: ['camera', 'photo', 'link', 'address', 'captureId'],
    telemetry_desc: ['installationId'],
    telemetry_health_desc: ['installationId', 'configuration', 'diagnostic'],
    telemetry_forget_desc: ['installationId', ...named('YA-WAMF')],
    downloads_desc: ['coordinates', ...named('GitHub', 'Google Storage', 'iNaturalist', 'Wikimedia')],
    garden_model_desc: ['automatic', ...named('GitHub')],
    model_repair_desc: named('GitHub'),
    fonts_desc: named('Google', 'IP'),
    photos_desc: named('Wikimedia', 'iNaturalist', 'IP'),
    osm_desc: named('OpenStreetMap', 'IP'),
    gbif_tiles_desc: named('GBIF', 'IP'),
    oauth_browser_desc: named('Gmail', 'Outlook', 'iNaturalist'),
    oauth_server_desc: ['account', ...named('Google', 'Microsoft', 'iNaturalist')],
    tests_desc: ['saved', 'email', 'token', 'key', ...named('Discord', 'Telegram', 'Pushover', 'placehold.co', 'BirdWeather')],
    diagnostics_desc: named('Frigate', 'iNaturalist', 'YA-WAMF')
};

const fold = (text: string): string => text.toLocaleLowerCase();

describe.each(LOCALES)('what leaves the network, in %s', (locale) => {
    const outbound = OUTBOUND[locale];

    it.each(Object.entries(REQUIRED))('%s keeps every disclosure', (key, disclosures) => {
        const text = outbound[key];
        expect(text, `${locale} ${key}`).toBeTruthy();
        for (const disclosure of disclosures) {
            const word = typeof disclosure === 'string' ? TERMS[disclosure][locale] : disclosure.name;
            expect(fold(text), `${locale} ${key} must say “${word}”`).toContain(fold(word));
        }
    });

    it('has a name and a description for every row the English list has', () => {
        for (const key of Object.keys(OUTBOUND.en)) expect(outbound[key], `${locale} ${key}`).toBeTruthy();
    });
});

describe('the disclosure table itself', () => {
    it('covers every description in the list, so a new row has to say what it discloses', () => {
        const described = Object.keys(OUTBOUND.en).filter((key) => key.endsWith('_desc') && key !== 'taxonomy_desc');
        // These say what a service is for and send only the name being looked up.
        const nameOnly = ['inat_desc', 'wikipedia_desc', 'gbif_desc', 'inat_submit_desc', 'updates_desc'];
        expect(described.filter((key) => !(key in REQUIRED) && !nameOnly.includes(key))).toEqual([]);
    });
});
