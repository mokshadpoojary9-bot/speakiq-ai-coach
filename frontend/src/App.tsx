import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { AnalysisSessionProvider } from './lib/session'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'

const Workspace = lazy(() => import('./pages/Workspace'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Twin = lazy(() => import('./pages/Twin'))
const Coach = lazy(() => import('./pages/Coach'))
const Reports = lazy(() => import('./pages/Reports'))

export default function App() {
  return (
    <AnalysisSessionProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="workspace" element={<Workspace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="twin" element={<Twin />} />
          <Route path="coach" element={<Coach />} />
          <Route path="reports" element={<Reports />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </AnalysisSessionProvider>
  )
}
