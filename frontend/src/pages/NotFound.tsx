import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button, EmptyState } from '../components/ui'

export default function NotFound() {
  return (
    <EmptyState icon={<Compass className="size-5" />} title="Page not found" action={<Link to="/"><Button variant="primary">Go to Diagnose</Button></Link>}>
      The address you opened does not exist.
    </EmptyState>
  )
}
