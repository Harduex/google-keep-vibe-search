import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`ErrorBoundary [${this.props.fallbackLabel ?? 'unknown'}]:`, error, info.componentStack);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-fallback">
          <span className="material-icons">warning</span>
          <p>
            Something went wrong{this.props.fallbackLabel ? ` in ${this.props.fallbackLabel}` : ''}.
          </p>
          {this.state.error && (
            <pre className="error-boundary-details">{this.state.error.message}</pre>
          )}
          <button className="error-boundary-retry" onClick={this.handleRetry}>
            <span className="material-icons">refresh</span>
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
