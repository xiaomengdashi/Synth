import { Navigate } from 'react-router-dom';

/** 旧路由兼容：配置已整合进单页配置中心。 */
export default function AdminModelSettings() {
  return <Navigate to="/admin/settings?tab=model" replace />;
}
