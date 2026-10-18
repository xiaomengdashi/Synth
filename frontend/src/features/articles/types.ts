export interface Article {
  id: string;
  title: string;
  summary: string;
  content_md: string;
  original_url: string;
  source_type: 'wechat' | 'bilibili' | 'youtube' | 'x' | 'csdn' | 'cnblogs' | 'other';
  cover_image_url?: string;
  account_name?: string;
  publish_time?: string;
  category?: string | null;
  created_at: string;
  /** 收藏/稍后读标记,后端新列;老数据与内存兜底路径可能缺省 */
  is_starred?: boolean;
  /** 阅读进度 0~1,已读由 isRead() 派生,后端不存派生布尔 */
  read_progress?: number;
}
