export interface Task {
  id: string;
  original_url: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  current_step: string;
  article_id?: string;
  created_at: string;
}
