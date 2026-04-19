import { useStore, Article } from '../store/useStore';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Video, FileText, Twitter, BookOpen, Code, Link as LinkIcon, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from '../utils/formatDate';

export default function Home() {
  const { articles, deleteArticle } = useStore();

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'wechat': return <FileText className="w-4 h-4 text-green-500" />;
      case 'bilibili': return <Video className="w-4 h-4 text-blue-400" />;
      case 'douyin': return <Video className="w-4 h-4 text-pink-500" />;
      case 'x': return <Twitter className="w-4 h-4 text-sky-500" />;
      case 'csdn': return <Code className="w-4 h-4 text-red-500" />;
      case 'cnblogs': return <BookOpen className="w-4 h-4 text-indigo-500" />;
      default: return <LinkIcon className="w-4 h-4 text-slate-500" />;
    }
  };

  const getSourceLabel = (sourceType: string) => {
    switch (sourceType) {
      case 'wechat': return '微信公众号';
      case 'bilibili': return 'Bilibili';
      case 'douyin': return '抖音';
      case 'x': return 'X (Twitter)';
      case 'csdn': return 'CSDN';
      case 'cnblogs': return '博客园';
      default: return '网页链接';
    }
  };

  return (
    <div className="space-y-16">
      {/* Hero Section */}
      <section className="relative pt-12 pb-20 text-center overflow-hidden rounded-3xl glass-panel shadow-2xl group">
        <div className="absolute inset-0 bg-gradient-to-b from-primary/10 to-transparent dark:from-primary/20 pointer-events-none" />
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative z-10 max-w-3xl mx-auto px-6"
        >
          <span className="inline-block py-1 px-3 rounded-full bg-primary/10 dark:bg-primary/20 text-primary dark:text-blue-300 text-sm font-semibold tracking-wider mb-6 border border-primary/20 shadow-inner">
            AI 驱动的资讯聚合平台
          </span>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-8 leading-tight">
            让知识流动
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-secondary animate-pulse">
              更智能，更高效
            </span>
          </h1>
          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-300 mb-10 max-w-2xl mx-auto leading-relaxed">
            将碎片化的短视频、冗长的公众号文章，通过大模型一键转化为结构化、易阅读的图文 Markdown 笔记。
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-4">
            <Link 
              to="/admin" 
              className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-xl bg-primary text-white font-bold text-lg hover:bg-blue-600 transition-all hover:shadow-[0_0_20px_rgba(59,130,246,0.5)] active:scale-95"
            >
              开始生成资讯 <ArrowRight className="w-5 h-5" />
            </Link>
            <a 
              href="#latest-articles" 
              className="inline-flex items-center justify-center px-8 py-4 rounded-xl bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white font-bold text-lg hover:bg-white/80 dark:hover:bg-slate-700/80 transition-all active:scale-95"
            >
              浏览最新
            </a>
          </div>
        </motion.div>
      </section>

      {/* Article Grid */}
      <section id="latest-articles" className="scroll-mt-24">
        <div className="flex items-center justify-between mb-10">
          <h2 className="text-3xl font-bold flex items-center gap-3 text-slate-900 dark:text-white">
            <div className="w-2 h-8 bg-primary rounded-full" />
            最新资讯
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {articles.map((article: Article, index: number) => (
            <motion.article
              key={article.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="group relative flex flex-col glass-panel rounded-2xl overflow-hidden hover:-translate-y-2 hover:shadow-[0_20px_40px_-15px_rgba(59,130,246,0.2)] transition-all duration-300"
            >
              <Link to={`/article/${article.id}`} className="block relative aspect-[16/9] overflow-hidden">
                <div className="absolute inset-0 bg-slate-900/20 group-hover:bg-transparent transition-colors z-10" />
                <img 
                  src={article.cover_image_url} 
                  alt={article.title}
                  className="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-700"
                />
                <div className="absolute top-4 left-4 z-20 flex items-center gap-1.5 px-3 py-1 rounded-full bg-black/60 backdrop-blur-md text-white text-xs font-medium border border-white/10 shadow-lg">
                  {getSourceIcon(article.source_type)}
                  {getSourceLabel(article.source_type)}
                </div>
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (window.confirm('确定要删除这篇文章吗？')) {
                      deleteArticle(article.id);
                    }
                  }}
                  className="absolute top-4 right-4 z-30 p-2 bg-white/90 dark:bg-slate-900/90 hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 hover:text-red-500 backdrop-blur-sm rounded-full shadow-sm opacity-0 group-hover:opacity-100 transition-all duration-200"
                  title="删除文章"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </Link>

              <div className="p-6 flex flex-col flex-1">
                <Link to={`/article/${article.id}`}>
                  <h3 className="text-xl font-bold mb-3 text-slate-900 dark:text-slate-100 group-hover:text-primary transition-colors line-clamp-2">
                    {article.title}
                  </h3>
                </Link>
                <p className="text-slate-600 dark:text-slate-400 text-sm mb-6 line-clamp-3 leading-relaxed">
                  {article.summary}
                </p>
                
                <div className="mt-auto flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-700/50">
                  <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{formatDistanceToNow(new Date(article.created_at))}前</span>
                  </div>
                  <Link 
                    to={`/article/${article.id}`}
                    className="text-primary text-sm font-semibold flex items-center gap-1 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all"
                  >
                    阅读全文 <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </div>
            </motion.article>
          ))}
        </div>
      </section>
    </div>
  );
}