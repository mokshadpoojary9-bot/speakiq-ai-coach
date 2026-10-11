import { Link } from 'react-router-dom'
import { btnPrimary, EmptyState } from '../components/ui'

export default function NotFound() {
  return (
    <EmptyState title="Page not found" description="There is nothing at this address.">
      <Link to="/" className={btnPrimary}>
        Back to the start
      </Link>
    </EmptyState>
  )
}
