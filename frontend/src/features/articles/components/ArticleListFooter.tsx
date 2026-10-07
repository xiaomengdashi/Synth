import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';

/** 滚动接近底部自动续载下一页文章(渐进式);筛选条件原样透传给后端。 */
export default function ArticleListFooter({ emptyCount, category, source, q, starred }: { emptyCount: number; category?: string; source?: string; q?: string; starred?: boolean }) {
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const hasMore = useAppStore((state) => state.articlesHasMore);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const check = () => {
      const node = sentinelRef.current;
      // 空列表时首屏请求由页面自己发;这里只负责在滚动接近哨兵时续载。
      // 不用 IntersectionObserver:实测部分 webview 不回调 observe 后的初始状态,续载会永久卡死
      if (!node || emptyCount === 0) return;
      if (node.getBoundingClientRect().top < window.innerHeight + 400) {
        void fetchArticles({ category, source, q, starred });
      }
    };
    window.addEventListener('scroll', check, { passive: true });
    check(); // 数据变化(本页加载完成)后立即复查:页面不够高时无需滚动也能续完
    return () => window.removeEventListener('scroll', check);
  }, [fetchArticles, emptyCount, category, source, q, starred]);

  if (!hasMore) {
    return emptyCount >= 5 ? (
      <p className="list-end-note">已加载全部文章</p>
    ) : null;
  }
  return (
    <div ref={sentinelRef} className="list-loading-note">
      <Loader2 size={14} className="animate-spin" /> 正在加载更多…
    </div>
  );
}
