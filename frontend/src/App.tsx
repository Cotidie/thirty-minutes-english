import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AskWidget } from './components/AskWidget'
import { AsksPage } from './pages/AsksPage'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:id" element={<SessionPage />} />
        <Route path="/asks" element={<AsksPage />} />
      </Routes>
      <AskWidget />
    </BrowserRouter>
  )
}
