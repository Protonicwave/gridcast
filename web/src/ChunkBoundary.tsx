import { Component, type ReactNode } from "react";

interface ChunkBoundaryProps {
  /** What failed, for the log, such as "the map". */
  readonly what: string;
  /** Shown in place of the children when they fail to load or draw. */
  readonly message: string;
  readonly children: ReactNode;
}

/** Keeps the page working when a lazily loaded part cannot be fetched or draws with an error. */
export class ChunkBoundary extends Component<ChunkBoundaryProps, { readonly failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override componentDidCatch(error: unknown) {
    console.error(`${this.props.what} failed to load or draw`, error);
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <p className="notice notice--warning" role="status">
        {this.props.message}
      </p>
    );
  }
}
