/**
 * WelcomePanel - Onboarding/welcome section for first-time users
 * Explains what the app does and how to get started
 */

import { useState, useEffect } from "react";

function WelcomePanel({ onDismiss }) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    // Check if user has seen welcome before
    const hasSeenWelcome = localStorage.getItem("tessiture_welcome_seen");
    if (hasSeenWelcome) {
      setIsVisible(false);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem("tessiture_welcome_seen", "true");
    setIsVisible(false);
    onDismiss?.();
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div className="welcome-panel card">
      <header className="card__header">
        <h2 className="card__title">🎤 Welcome to Tessiture</h2>
        <p className="card__meta">Your personal vocal analysis coach</p>
      </header>

      <div className="welcome-panel__content">
        <p className="welcome-panel__intro">
          Tessiture analyzes your singing voice and gives you plain-language feedback to help you improve.
          Here's what you can do:
        </p>

        <div className="welcome-panel__features">
          <div className="welcome-panel__feature">
            <span className="welcome-panel__feature-icon">🔬</span>
            <h3 className="welcome-panel__feature-title">Analyze your voice</h3>
            <p className="welcome-panel__feature-desc">
              Upload a recording to discover your vocal range, comfortable tessitura, and personalized practice tips.
            </p>
          </div>

          <div className="welcome-panel__feature">
            <span className="welcome-panel__feature-icon">🎯</span>
            <h3 className="welcome-panel__feature-title">Compare to a reference</h3>
            <p className="welcome-panel__feature-desc">
              Sing along with a reference track and see how closely your pitch and rhythm match.
            </p>
          </div>

          <div className="welcome-panel__feature">
            <span className="welcome-panel__feature-icon">🎵</span>
            <h3 className="welcome-panel__feature-title">Try a demo</h3>
            <p className="welcome-panel__feature-desc">
              Not sure where to start? Pick a demo track from the Example Library — no upload needed.
            </p>
          </div>
        </div>

        <div className="welcome-panel__actions">
          <button
            type="button"
            className="button button--primary"
            onClick={handleDismiss}
          >
            Get started →
          </button>
          <button
            type="button"
            className="button button--secondary"
            onClick={handleDismiss}
          >
            Don't show again
          </button>
        </div>
      </div>
    </div>
  );
}

export default WelcomePanel;
