import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { initializeServerTimeZone } from './utils/formatDate'
import './index.css'
import './styles/workspace.css'
import './styles/settings.css'
import './styles/fetch-priorities.css'
import './styles/admin-system.css'

async function mountApp() {
  await initializeServerTimeZone()
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void mountApp()
