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
        <a className="studio-brand" href="/xrd" aria-label="MATERIAI XRD Studio 홈">
          <span className="studio-mark" aria-hidden="true">
            <span className="studio-mark-letter">M</span>
            <span className="studio-mark-signal" />
          </span>
          <span className="studio-brand-copy">
            <span className="studio-wordmark">MATERIAI</span>
            <span className="studio-product-name">XRD Studio <em>LAB</em></span>
          </span>
        </a>
        <div className="studio-header-actions">
          <div className="studio-suite" aria-hidden="true">
            <span>MATERIALS INTELLIGENCE</span>
            <strong>X-RAY DIFFRACTION</strong>
          </div>
          <span className="studio-system-status"><i aria-hidden="true" />분석 엔진 준비됨</span>
          <button type="button" onClick={() => document.getElementById('studio-settings')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
            <span className="material-symbols-rounded" aria-hidden="true">tune</span>
            작업 설정
          </button>
        </div>
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
