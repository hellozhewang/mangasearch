import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary, { reportClientError } from './components/ErrorBoundary'

window.addEventListener('error', (e) =>
  reportClientError('window-error', String(e.message), e.error?.stack),
)
window.addEventListener('unhandledrejection', (e) => {
  const reason = e.reason as { message?: string; stack?: string } | undefined
  reportClientError('unhandled-rejection', String(reason?.message ?? e.reason), reason?.stack)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
