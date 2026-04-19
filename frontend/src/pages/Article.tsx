import { useParams, Link } from 'react-router-dom';
import { useStore, Article as ArticleType } from '../store/useStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import hljs from 'highlight.js';
import 'highlight.js/styles/github-dark.css'; // 使用更经典美观的 GitHub Dark 主题
import { motion } from 'framer-motion';
import { ArrowLeft, ExternalLink, Calendar, Link as LinkIcon, Loader2 } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';

export default function Article() {
  const { id } = useParams<{ id: string }>();
  const storeArticle = useStore((state) => state.articles.find((a) => a.id === id));
  
  const [article, setArticle] = useState<ArticleType | null>(storeArticle || null);
  const [loading, setLoading] = useState(!storeArticle);
  const [error, setError] = useState(false);

  const htmlContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 如果 store 中没有找到，说明可能是刷新了页面，尝试从后端拉取
    if (!storeArticle && id) {
      setLoading(true);
      fetch(`/api/v1/articles/${id}`)
        .then(res => {
          if (!res.ok) throw new Error('Article not found');
          return res.json();
        })
        .then(data => {
          // 因为后端返回的可能是单个对象，或者是 {data: [...]} 格式
          // 这里的单个文章接口返回的是单个对象
          setArticle(data);
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          setError(true);
          setLoading(false);
        });
    } else if (storeArticle) {
      setArticle(storeArticle);
    }
  }, [id, storeArticle]);

  // 针对渲染原始 HTML 内容的高亮处理
  useEffect(() => {
    if (article && htmlContainerRef.current) {
      // 找到所有 pre code 或 class 包含 language- 的块
      const blocks = htmlContainerRef.current.querySelectorAll('pre code, .code-snippet, [class*="language-"]');
      blocks.forEach((block) => {
        // CSDN 特殊处理：有时候代码块只是一堆 span，需要让 hljs 重新着色
        hljs.highlightElement(block as HTMLElement);
      });
    }
  }, [article]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-slate-500">加载文章中...</p>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh]">
        <h2 className="text-2xl font-bold mb-4">文章未找到</h2>
        <Link to="/" className="text-primary hover:underline flex items-center gap-2">
          <ArrowLeft className="w-4 h-4" /> 返回首页
        </Link>
      </div>
    );
  }

  return (
    <motion.article 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="max-w-4xl mx-auto"
    >
      <Link 
        to="/" 
        className="inline-flex items-center gap-2 text-slate-500 hover:text-primary transition-colors mb-8"
      >
        <ArrowLeft className="w-4 h-4" /> 返回首页
      </Link>

      <div className="glass-panel rounded-3xl overflow-hidden shadow-xl">
        {/* Cover Image */}
        <div className="relative w-full h-64 sm:h-80 md:h-[400px] overflow-hidden">
          <img 
            src={article.cover_image_url} 
            alt={article.title}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/20 to-transparent" />
          
          <div className="absolute bottom-0 left-0 w-full p-6 md:p-10">
            <div className="flex items-center gap-4 text-white/80 text-sm font-medium mb-4">
              <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-md px-3 py-1 rounded-full">
                <Calendar className="w-4 h-4" />
                {new Date(article.created_at).toLocaleDateString('zh-CN')}
              </span>
              <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-md px-3 py-1 rounded-full">
                <LinkIcon className="w-4 h-4" />
                {article.source_type.toUpperCase()}
              </span>
            </div>
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-extrabold text-white leading-tight">
              {article.title}
            </h1>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 md:p-10 lg:p-12 bg-white dark:bg-slate-900">
          <div className="flex justify-end mb-8">
            <a 
              href={article.original_url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-primary hover:text-white transition-all text-sm font-medium"
            >
              <ExternalLink className="w-4 h-4" /> 查看原文
            </a>
          </div>

          <div className="prose prose-slate dark:prose-invert max-w-none prose-img:rounded-xl prose-img:shadow-lg prose-headings:font-bold prose-a:text-primary hover:prose-a:text-blue-400 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800">
            {article.content_md.includes('<!-- HTML_CONTENT_START -->') ? (
              <>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                >
                  {article.content_md.split('<!-- HTML_CONTENT_START -->')[0]}
                </ReactMarkdown>
                <div 
                  ref={htmlContainerRef}
                  className="mt-8 pt-8 border-t border-slate-200 dark:border-slate-800 w-full overflow-hidden article-html-container"
                  dangerouslySetInnerHTML={{ 
                    __html: article.content_md.split('<!-- HTML_CONTENT_START -->')[1].replace('<!-- HTML_CONTENT_END -->', '') 
                  }}
                />
              </>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {article.content_md}
              </ReactMarkdown>
            )}
          </div>
        </div>
      </div>
    </motion.article>
  );
}