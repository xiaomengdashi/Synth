export interface AppConfig {
  modelName: string;
  apiKey: string;
  apiKeyConfigured?: boolean;
  baseUrl: string;
  tikhubConfigured?: boolean;
  minimaxApiKey?: string;
  minimaxConfigured?: boolean;
  imapHost?: string;
  imapUser?: string;
  imapPassword?: string;
  imapSenderWhitelist?: string;
  imapConfigured?: boolean;
  // 可调参数：留空即恢复默认（后端 SETTING_DEFAULTS 兜底）
  tikhubApiBase?: string;
  bilibiliProxy?: string;
  minimaxApiBase?: string;
  llmTemperature?: string;
  llmMaxTokens?: string;
  llmTimeoutSeconds?: string;
  summaryLength?: string;
  notesPrompt?: string;
  emailFetchDays?: string;
}
