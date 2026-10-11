import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { SettingsButton } from './components/SettingsButton'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:id" element={<SessionPage />} />
      </Routes>
      <SettingsButton />
    </BrowserRouter>
  )
}
