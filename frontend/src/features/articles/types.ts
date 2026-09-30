export interface Article {
  id: string;
  title: string;
  summary: string;
  content_md: string;
  original_url: string;
  source_type: 'wechat' | 'bilibili' | 'douyin' | 'x' | 'csdn' | 'cnblogs' | 'other';
  cover_image_url?: string;
  account_name?: string;
  publish_time?: string;
  created_at: string;
}
