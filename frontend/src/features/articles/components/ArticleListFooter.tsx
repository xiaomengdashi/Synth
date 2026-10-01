import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useAppStore } from '../../app/store/useAppStore';

/** 滚动到底自动续载下一页文章(渐进式,每次 5 篇);筛选条件原样透传给后端。 */
export default function ArticleListFooter({ emptyCount, category, source, q }: { emptyCount: number; category?: string; source?: string; q?: string }) {
  const fetchArticles = useAppStore((state) => state.fetchArticles);
  const hasMore = useAppStore((state) => state.articlesHasMore);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) void fetchArticles({ category, source, q });
    }, { rootMargin: '400px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [fetchArticles, emptyCount, category, source, q]);

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
