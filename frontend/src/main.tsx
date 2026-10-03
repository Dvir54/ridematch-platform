import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { createQueryClient } from './api/queryClient'
import { AuthProvider } from './auth/AuthProvider'
import { startMocks } from './mocks/start'
import { initMonitoring } from './monitoring'
// Self-hosted, so no visitor IP goes to Google Fonts (plan §11.8).
import '@fontsource-variable/archivo/wght.css'
import '@fontsource-variable/archivo/wght-italic.css'
import './index.css'

const container = document.getElementById('root')
if (!container) throw new Error('index.html is missing its #root element')

initMonitoring()
const queryClient = createQueryClient()

// Mocks must intercept before the first query runs, so mount after they start.
void startMocks().then(() => {
  createRoot(container).render(
    <StrictMode>
      <ErrorBoundary>
        <BrowserRouter>
          <AuthProvider>
            <QueryClientProvider client={queryClient}>
              <App />
            </QueryClientProvider>
          </AuthProvider>
        </BrowserRouter>
      </ErrorBoundary>
    </StrictMode>,
  )
})
