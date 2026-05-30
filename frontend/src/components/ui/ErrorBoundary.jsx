import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Section render failed', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
          <p className="text-white font-medium">Something went wrong in this section.</p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            className="mt-3 px-3 py-1.5 rounded-lg bg-zinc-800 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
