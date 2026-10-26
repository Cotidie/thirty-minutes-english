import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { CornerTools } from './components/CornerTools'
import { CorpusPage } from './pages/CorpusPage'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:id" element={<SessionPage />} />
        <Route path="/corpus" element={<CorpusPage />} />
      </Routes>
      <CornerTools />
    </BrowserRouter>
  )
}
