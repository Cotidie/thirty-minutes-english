import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:id" element={<SessionPage />} />
      </Routes>
    </BrowserRouter>
  )
}
