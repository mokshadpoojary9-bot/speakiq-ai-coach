import { Suspense, useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { HealthStatus } from './HealthStatus'
import { LoadingState } from './ui'

const navItems = [
  { to: '/workspace', label: 'Workspace' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/twin', label: 'Acoustic Twin' },
  { to: '/coach', label: 'Evidence Coach' },
  { to: '/reports', label: 'Reports' },
]

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
      <rect width="32" height="32" rx="7" className="fill-ink-700" />
      <g className="fill-accent">
        <rect x="6" y="13" width="3" height="6" rx="1.5" />
        <rect x="11" y="8" width="3" height="16" rx="1.5" />
        <rect x="16" y="11" width="3" height="10" rx="1.5" />
        <rect x="21" y="5" width="3" height="22" rx="1.5" />
      </g>
    </svg>
  )
}

export function Layout() {
  const { pathname } = useLocation()

  // Each page starts at the top instead of inheriting the previous page's scroll position.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-ink-950"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 border-b border-line bg-ink-900/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 sm:px-6 md:flex-row md:items-center md:justify-between">
          <Link to="/" className="flex items-center gap-2.5 self-start rounded-lg text-base font-semibold tracking-tight">
            <Logo />
            SpeakIQ <span className="font-normal text-muted">AI Coach</span>
          </Link>
          <nav aria-label="Primary" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <ul className="flex gap-1">
              {navItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      `block rounded-lg px-3 py-2 text-sm whitespace-nowrap transition-colors ${
                        isActive ? 'bg-ink-700 text-accent' : 'text-muted hover:bg-ink-800 hover:text-fg'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 outline-none sm:px-6 sm:py-14">
        <Suspense fallback={<LoadingState label="Loading page…" />}>
          <Outlet />
        </Suspense>
      </main>

      <footer className="border-t border-line print:hidden">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>SpeakIQ AI Coach · Demo data is always labelled as such.</p>
          <HealthStatus />
        </div>
      </footer>
    </div>
  )
}
