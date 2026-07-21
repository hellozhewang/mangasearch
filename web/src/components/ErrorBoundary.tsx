import { Component, type ErrorInfo, type ReactNode } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'

export function reportClientError(kind: string, message: string, stack?: string) {
  try {
    fetch('/api/client-error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind,
        message,
        stack,
        url: location.href,
        ua: navigator.userAgent,
      }),
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* reporting must never throw */
  }
}

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Catches render crashes: shows a real message instead of a white page and
 *  reports the stack to the server log. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportClientError(
      'react-crash',
      error.message,
      `${error.stack ?? ''}\nComponent stack:${info.componentStack ?? ''}`,
    )
  }

  render() {
    if (this.state.error) {
      return (
        <Alert
          severity="error"
          sx={{ m: 3 }}
          action={
            <Button color="inherit" size="small" onClick={() => location.reload()}>
              Reload
            </Button>
          }
        >
          The app crashed: {this.state.error.message} — details were reported to the
          server log (burger menu → Server logs).
        </Alert>
      )
    }
    return this.props.children
  }
}
