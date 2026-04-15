import React from "react";

export default function Layout({
  title = "The Ledger | Business Network",
  user = null,
  subtitle = "Connected to Django APIs",
  messages = [],
  children,
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <a href="/index/" className="brand-link">
            <div className="brand-badge">
              L
            </div>
            <div>
              <h1 className="brand-title">{title}</h1>
              <p className="brand-subtitle">{subtitle}</p>
            </div>
            <span className="brand-version">
              v2.0
            </span>
          </a>
        </div>

        <div className="user-wrap">
          {user ? (
            <>
              <div className="user-meta">
                <span className="user-email">{user.email}</span>
                <span className="user-tag">Verified Node</span>
              </div>
              <form method="post" action="/logout/" className="logout-form">
                <input type="hidden" name="csrfmiddlewaretoken" value={window.CSRF_TOKEN || ""} />
                <button type="submit" className="btn btn-logout">
                Sign Out
                </button>
              </form>
            </>
          ) : (
            <>
              <a href="/login/" className="nav-link">
                Log In
              </a>
              <a
                href="/signup/"
                className="btn"
              >
                Sign Up
              </a>
            </>
          )}
        </div>
      </header>

      <main className="main-content">
        <div id="toast-container" className="toast-container">
            {messages.map((message, index) => (
              <div
                key={`${message}-${index}`}
              className="toast"
              >
              <span>{message}</span>
              </div>
            ))}
          </div>
        <section className="content-wrap">{children}</section>
      </main>
    </div>
  );
}