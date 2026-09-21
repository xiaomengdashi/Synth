import { ArrowRight, Clock3, FileText, Twitter, Video } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import type { Article } from '../types';
import { formatDistanceToNow } from '../../../utils/formatDate';

function sourceLabel(sourceType: Article['source_type']) {
  if (sourceType === 'wechat') return '微信公众号';
  if (sourceType === 'bilibili') return 'Bilibili';
  if (sourceType === 'x') return 'X / Twitter';
  return '网页链接';
}

function SourceIcon({ sourceType }: { sourceType: Article['source_type'] }) {
  const Icon = sourceType === 'wechat' ? FileText : sourceType === 'bilibili' ? Video : Twitter;
  return <Icon size={12} />;
}

export default function ArticleList({ articles, emptyMessage }: { articles: Article[]; emptyMessage?: string }) {
  return (
    <div className="article-grid">
      <AnimatePresence initial={false}>
        {articles.length === 0 ? <div className="empty-state">{emptyMessage || '还没有文章。粘贴一条链接，开始建立你的第一篇知识卡片。'}</div> : articles.map((article, index) => (
          <motion.article key={article.id} className="article-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .04 }}>
            <Link to={`/article/${article.id}`} className="article-cover">
              <img src={article.cover_image_url || '/favicon.svg'} alt={article.title} />
              <span className="source-tag"><SourceIcon sourceType={article.source_type} /> {sourceLabel(article.source_type)}</span>
            </Link>
            <div className="article-body">
              <Link to={`/article/${article.id}`} style={{ textDecoration: 'none' }}><h3>{article.title}</h3></Link>
              <p>{article.summary}</p>
              <div className="article-meta"><span><Clock3 size={11} style={{ verticalAlign: 'middle', marginRight: 5 }} />{formatDistanceToNow(new Date(article.created_at))}前</span><span className="read-arrow"><ArrowRight size={14} /></span></div>
            </div>
          </motion.article>
        ))}
      </AnimatePresence>
    </div>
  );
}
