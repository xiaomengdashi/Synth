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
}
