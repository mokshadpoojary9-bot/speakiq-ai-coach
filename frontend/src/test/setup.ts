import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// jsdom has no layout, WebGL or object URLs. These stubs describe that environment honestly:
// charts get a size observer that never fires and canvases report that WebGL is unavailable.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext

URL.createObjectURL = () => 'blob:test-audio'
URL.revokeObjectURL = () => {}

// The layout footer checks the backend; tests run without one.
vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('no backend in tests')))
