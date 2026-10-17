import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Callout } from './ui'

interface State {
  error: Error | null
}

/** Keeps one broken page from taking down the whole app. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <Callout
        tone="critical"
        title="Something went wrong on this page"
        action={
          <Button size="sm" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        }
      >
        <code className="text-xs">{this.state.error.message}</code>
      </Callout>
    )
  }
}
