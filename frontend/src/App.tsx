import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { CornerTools } from './components/CornerTools'
import { DatabasePage } from './pages/DatabasePage'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:id" element={<SessionPage />} />
        <Route path="/database" element={<DatabasePage tab="expressions" />} />
        <Route path="/database/topics" element={<DatabasePage tab="topics" />} />
      </Routes>
      <CornerTools />
    </BrowserRouter>
  )
}
