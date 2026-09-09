import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ToolbarContentProvider } from './context/ToolbarContentContext';
import Toolbar from './components/Toolbar';
import XRDAnalyzer from './pages/XRD/XRDAnalyzer';
import './App.css';

function AppContent() {
  return (
    <ToolbarContentProvider>
      <header className="studio-header">
        <a className="studio-brand" href="/xrd"><span className="studio-mark" aria-hidden="true">∿</span><span>XRD <strong>Studio</strong><small>패턴에서 데이터로</small></span></a>
        <div className="studio-header-actions"><span className="studio-version">DIGITIZE / ANALYZE</span><button type="button" onClick={() => document.getElementById('studio-settings')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>설정 패널 ↗</button></div>
      </header>
      <div className="frame-changable xrd-standalone">
        <div className="frame-changable-child xrd-main">
          <div id="main-contents-container">
            <div className="main-route-outlet">
              <Routes>
                <Route
                  path="/xrd"
                  element={
                    <div className="tools-collection-root box-col pd0 gap10">
                      <XRDAnalyzer />
                    </div>
                  }
                />
                <Route path="/" element={<Navigate to="/xrd" replace />} />
                <Route path="*" element={<Navigate to="/xrd" replace />} />
              </Routes>
            </div>
          </div>
        </div>
        <aside id="studio-settings" aria-label="분석 설정" className="frame-changable-child xrd-toolbar">
          <Toolbar />
        </aside>
      </div>
    </ToolbarContentProvider>
  );
}

export default function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}
