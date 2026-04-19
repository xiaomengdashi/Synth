import React, { useState, useEffect } from 'react';
import { useStore, Task } from '../store/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Plus, Link as LinkIcon, AlertCircle, CheckCircle2, Loader2, ArrowRight, XCircle, Settings2, Key, Globe, Cpu, Video } from 'lucide-react';
import { formatDistanceToNow } from '../utils/formatDate';

export default function Admin() {
  const { tasks, addTask, updateTask, addArticle, config, setConfig, fetchConfig } = useStore();
  const [url, setUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [configType, setConfigType] = useState<'llm' | 'bilibili'>('llm');
  const [localConfig, setLocalConfig] = useState(config);
  
  // 新增状态：大模型验证和列表
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState<'success' | 'error' | null>(null);
  const [verifyMessage, setVerifyMessage] = useState('');

  // 初始化加载后端保存的配置
  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // 当全局 config 改变时同步到 localConfig
  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  // 处理 API Key 显示（只显示前4位和后2位）
  const getDisplayApiKey = (key: string) => {
    if (!key) return '';
    if (key.length <= 6) return key;
    return `${key.slice(0, 4)}...${key.slice(-2)}`;
  };

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setLocalConfig({...localConfig, apiKey: newValue});
  };

  const handleVerify = async () => {
    // 验证时使用原始 apiKey，如果是带省略号的，说明未修改，使用全局 config 的 key
    let finalApiKey = localConfig.apiKey;
    if (finalApiKey.includes('...') || finalApiKey === '') {
      finalApiKey = config.apiKey;
    }

    if (!finalApiKey || !localConfig.baseUrl) {
      setVerifyStatus('error');
      setVerifyMessage('请先输入 Base URL 和 API Key');
      return;
    }

    setIsVerifying(true);
    setVerifyStatus(null);
    setVerifyMessage('');

    try {
      const response = await fetch('/api/v1/config/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey: finalApiKey,
          baseUrl: localConfig.baseUrl
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || '验证失败');
      }

      setAvailableModels(data.models || []);
      setVerifyStatus('success');
      setVerifyMessage('验证成功！已获取可用模型列表。');
      
      // 如果当前没有选中模型且有可用模型，自动选中第一个
      if (!localConfig.modelName && data.models && data.models.length > 0) {
        setLocalConfig({ ...localConfig, modelName: data.models[0] });
      }

    } catch (err: any) {
      setVerifyStatus('error');
      setVerifyMessage(err.message || '验证失败，请检查配置');
      setAvailableModels([]);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleConfigSave = (e: React.FormEvent) => {
    e.preventDefault();
    // 如果用户提交的是脱敏后的格式（说明没修改），则直接保存原有的 config.apiKey
    const finalConfig = { ...localConfig };
    if (finalConfig.apiKey.includes('...')) {
      finalConfig.apiKey = config.apiKey;
    }
    setConfig(finalConfig);
    setShowConfig(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    if (!config.apiKey) {
      alert("请先配置大模型 API Key！");
      setShowConfig(true);
      return;
    }

    setIsSubmitting(true);
    
    const taskId = Math.random().toString(36).substr(2, 9);
    const newTask: Task = {
      id: taskId,
      original_url: url,
      status: 'pending',
      current_step: '初始化任务...',
      created_at: new Date().toISOString()
    };
    addTask(newTask);
    setUrl('');

    try {
      const response = await fetch('/api/v1/tasks/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: url,
          config: config
        }),
      });

      if (!response.ok) {
        throw new Error('提交任务失败');
      }

      const data = await response.json();
      
      // 开始轮询任务状态
      pollTaskStatus(data.task_id, taskId);
    } catch (error) {
      updateTask(taskId, { 
        status: 'failed', 
        current_step: `提交失败: ${error instanceof Error ? error.message : '未知错误'}` 
      });
      setIsSubmitting(false);
    }
  };

  const pollTaskStatus = async (backendTaskId: string, localTaskId: string) => {
    let isCompleted = false;
    let pollCount = 0;
    const maxPolls = 120; // 最大轮询次数 (120次 * 2秒 = 4分钟)

    while (!isCompleted && pollCount < maxPolls) {
      try {
        const response = await fetch(`/api/v1/tasks/${backendTaskId}/status`);
        if (response.ok) {
          const data = await response.json();
          
          updateTask(localTaskId, {
            status: data.status,
            current_step: data.current_step,
            article_id: data.article_id
          });

          if (data.status === 'completed' || data.status === 'failed') {
            isCompleted = true;
            setIsSubmitting(false);
            
            // 如果完成了并且有文章数据，我们手动拉取一次并添加到 store，同时也重新拉取最新列表
            if (data.status === 'completed' && data.article) {
               addArticle(data.article);
               useStore.getState().fetchArticles();
            }
            break;
          }
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
      
      pollCount++;
      await new Promise(resolve => setTimeout(resolve, 2000)); // 2秒轮询一次
    }
    
    if (!isCompleted) {
      updateTask(localTaskId, { status: 'failed', current_step: '任务处理超时' });
      setIsSubmitting(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending': return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'processing': return <Loader2 className="w-5 h-5 text-primary animate-spin" />;
      case 'completed': return <CheckCircle2 className="w-5 h-5 text-secondary" />;
      case 'failed': return <XCircle className="w-5 h-5 text-red-500" />;
      default: return <AlertCircle className="w-5 h-5 text-slate-500" />;
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">管理控制台</h1>
          <p className="text-slate-600 dark:text-slate-400">提交链接并监控 AI 处理流水线</p>
        </div>
        
        <div className="flex gap-3">
          <button
            onClick={() => {
              setLocalConfig(config);
              setConfigType('llm');
              setShowConfig(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl font-medium transition-colors"
          >
            <Settings2 className="w-5 h-5" />
            大模型配置
          </button>
          <button
            onClick={() => {
              setLocalConfig(config);
              setConfigType('bilibili');
              setShowConfig(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded-xl font-medium transition-colors"
          >
            <Video className="w-5 h-5" />
            B站配置
          </button>
        </div>
      </div>

      {/* Configuration Panel */}
      <AnimatePresence>
        {showConfig && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <form onSubmit={handleConfigSave} className="glass-panel p-6 sm:p-8 rounded-3xl relative overflow-hidden">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  {configType === 'llm' ? (
                    <><Settings2 className="w-5 h-5 text-primary" />大模型配置</>
                  ) : (
                    <><Video className="w-5 h-5 text-blue-500" />Bilibili 抓取配置</>
                  )}
                </h3>
                <button
                  type="button"
                  onClick={() => setShowConfig(false)}
                  className="p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              {configType === 'llm' ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
                        <Globe className="w-4 h-4" /> Base URL
                      </label>
                      <input
                        type="url"
                        value={localConfig.baseUrl}
                        onChange={(e) => setLocalConfig({...localConfig, baseUrl: e.target.value})}
                        placeholder="https://api.openai.com/v1"
                        className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                        required
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
                        <Key className="w-4 h-4" /> API Key
                      </label>
                      <input
                        type="text"
                        value={localConfig.apiKey === config.apiKey && config.apiKey ? getDisplayApiKey(config.apiKey) : localConfig.apiKey}
                        onFocus={() => {
                          if (localConfig.apiKey === config.apiKey && config.apiKey.length > 6) {
                            setLocalConfig({...localConfig, apiKey: ''});
                          }
                        }}
                        onChange={handleApiKeyChange}
                        placeholder="sk-..."
                        className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                        required
                      />
                    </div>
                  </div>

                  {/* 验证和模型选择区域 */}
                  <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-100 dark:border-slate-700/50 space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        输入 Base URL 和 API Key 后，可验证并自动获取模型列表。
                      </p>
                      <button
                        type="button"
                        onClick={handleVerify}
                        disabled={isVerifying || !localConfig.baseUrl || !localConfig.apiKey}
                        className="px-4 py-2 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-200 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        {isVerifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                        验证并获取模型
                      </button>
                    </div>

                    {verifyStatus && (
                      <div className={`text-sm p-3 rounded-lg flex items-center gap-2 ${verifyStatus === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400' : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'}`}>
                        {verifyStatus === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                        {verifyMessage}
                      </div>
                    )}

                    <div className="space-y-2 pt-2">
                      <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
                        <Cpu className="w-4 h-4" /> 模型名称 (选择或手动输入)
                      </label>
                      {availableModels.length > 0 ? (
                        <select
                          value={localConfig.modelName}
                          onChange={(e) => setLocalConfig({...localConfig, modelName: e.target.value})}
                          className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                          required
                        >
                          <option value="" disabled>请选择模型</option>
                          {availableModels.map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={localConfig.modelName}
                          onChange={(e) => setLocalConfig({...localConfig, modelName: e.target.value})}
                          placeholder="如: gpt-4o, deepseek-chat"
                          className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                          required
                        />
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="space-y-4">
                  <div className="mb-4">
                    <p className="text-sm text-slate-500 dark:text-slate-400 flex items-start gap-1.5 bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg border border-blue-100 dark:border-blue-800/30">
                      <AlertCircle className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                      <span>填写 Bilibili 网页版的 Cookie 可以突破风控和匿名限制，大幅提高获取 AI 专属字幕的成功率。留空则使用默认匿名抓取。</span>
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                      SESSDATA
                    </label>
                    <input
                      type="password"
                      value={localConfig.biliSessdata || ''}
                      onChange={(e) => setLocalConfig({ ...localConfig, biliSessdata: e.target.value })}
                      className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 text-slate-900 dark:text-white font-mono text-sm"
                      placeholder="填入浏览器的 SESSDATA Cookie"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                        bili_jct
                      </label>
                      <input
                        type="password"
                        value={localConfig.biliJct || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, biliJct: e.target.value })}
                        className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 text-slate-900 dark:text-white font-mono text-sm"
                        placeholder="bili_jct Cookie"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                        buvid3
                      </label>
                      <input
                        type="password"
                        value={localConfig.biliBuvid3 || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, biliBuvid3: e.target.value })}
                        className="w-full px-4 py-2.5 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 text-slate-900 dark:text-white font-mono text-sm"
                        placeholder="buvid3 Cookie"
                      />
                    </div>
                  </div>
                </div>
              )}
              
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowConfig(false)}
                  className="px-6 py-2.5 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 bg-primary hover:bg-blue-600 text-white rounded-lg font-medium transition-colors"
                >
                  保存配置
                </button>
              </div>
            </form>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Submission Panel */}
      <section className="glass-panel p-8 rounded-3xl relative overflow-hidden group">
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-primary/10 dark:bg-primary/5 rounded-full blur-3xl pointer-events-none group-hover:bg-primary/20 transition-colors duration-700" />
        
        <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
          <Plus className="w-5 h-5 text-primary" /> 新建任务
        </h2>
        
        <form onSubmit={handleSubmit} className="relative">
          <div className="flex flex-col sm:flex-row gap-4 relative z-10">
            <div className="flex-1 relative">
              <LinkIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="粘贴微信公众号、B站或抖音链接..."
                className="w-full pl-12 pr-4 py-4 bg-white/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 text-slate-900 dark:text-white placeholder:text-slate-400 shadow-sm transition-all text-lg"
                required
              />
            </div>
            <button
              type="submit"
              disabled={isSubmitting || !url.trim()}
              className="px-8 py-4 bg-primary hover:bg-blue-600 text-white rounded-xl font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 min-w-[140px] shadow-lg shadow-primary/20 hover:shadow-primary/40 active:scale-95"
            >
              {isSubmitting ? (
                <><Loader2 className="w-5 h-5 animate-spin" /> 提交中</>
              ) : (
                <>开始处理 <ArrowRight className="w-5 h-5" /></>
              )}
            </button>
          </div>
        </form>
      </section>

      {/* Tasks Monitoring */}
      <section>
        <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
          <Loader2 className="w-5 h-5 text-primary" /> 任务监控
        </h2>
        
        <div className="space-y-4">
          <AnimatePresence>
            {tasks.length === 0 ? (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-center py-12 text-slate-500 dark:text-slate-400 glass-panel rounded-2xl border-dashed"
              >
                暂无处理任务，请在上方提交链接。
              </motion.div>
            ) : (
              tasks.map((task) => (
                <motion.div
                  key={task.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className="glass-panel p-5 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
                >
                  <div className="flex items-start gap-4 flex-1 overflow-hidden w-full">
                    <div className="mt-1 flex-shrink-0">
                      {getStatusIcon(task.status)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-500 dark:text-slate-400 truncate mb-1">
                        {task.original_url}
                      </p>
                      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                        <span className="font-medium text-slate-900 dark:text-slate-100 flex items-center gap-2">
                          状态: {task.current_step}
                          {task.status === 'processing' && (
                            <span className="flex gap-1">
                              <span className="w-1 h-1 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                              <span className="w-1 h-1 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                              <span className="w-1 h-1 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                            </span>
                          )}
                        </span>
                        <span className="text-xs text-slate-400">
                          {formatDistanceToNow(new Date(task.created_at))}前
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  {task.status === 'completed' && task.article_id && (
                    <Link
                      to={`/article/${task.article_id}`}
                      className="shrink-0 px-4 py-2 bg-secondary/10 text-secondary hover:bg-secondary/20 rounded-lg text-sm font-medium transition-colors border border-secondary/20"
                    >
                      查看文章
                    </Link>
                  )}
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
}