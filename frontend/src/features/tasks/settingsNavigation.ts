export const SETTINGS_GROUPS = [
  {
    label: '内容获取', path: '/admin/tikhub',
    items: [
      { id: 'priorities', label: '获取优先级', path: '/admin/tikhub' },
      { id: 'twitter-cli', label: 'X 登录配置', path: '/admin/tikhub' },
      { id: 'account', label: 'TikHub 账户', path: '/admin/tikhub' },
      { id: 'network', label: '网络配置', path: '/admin/tikhub' },
      { id: 'query', label: '多平台查询', path: '/admin/tikhub/query' },
    ],
  },
  {
    label: '模型服务', path: '/admin/model',
    items: [
      { id: 'connection', label: '模型连接', path: '/admin/model' },
      { id: 'transcription', label: '语音转写', path: '/admin/model' },
      { id: 'generation', label: '生成参数', path: '/admin/model' },
    ],
  },
  {
    label: '访问安全', path: '/admin/token',
    items: [{ id: 'token', label: '访问令牌', path: '/admin/token' }],
  },
];

export function activeSettingsItem(pathname: string, search: string) {
  const group = SETTINGS_GROUPS.find(group => group.items.some(item => item.path === pathname));
  if (!group) return undefined;
  const requested = new URLSearchParams(search).get('section');
  const candidates = group.items.filter(item => item.path === pathname);
  return candidates.find(item => item.id === requested) ?? candidates[0];
}
