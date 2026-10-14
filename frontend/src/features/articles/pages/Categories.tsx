import { Navigate, useSearchParams } from 'react-router-dom';
export default function Categories() {
  const [params] = useSearchParams();
  return <Navigate to={`/articles${params.size ? `?${params.toString()}` : ''}`} replace />;
}
