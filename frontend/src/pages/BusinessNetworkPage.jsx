import React from "react";
import Layout from "../components/Layout";

export default function BusinessNetworkPage({
  businesses = [],
  user,
  formData,
  formErrors,
  isCreating,
  onFormChange,
  onSubmitCreateEntity,
  onOpenEntity,
}) {
  return (
    <Layout user={user} subtitle="React + Django integration complete">
      <div className="dashboard">
        <div className="hero">
          <div>
            <h2>Business Network</h2>
            <p>Manage all business entities from React while your Django backend remains the source of truth.</p>
          </div>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Active Units</div>
            <div className="stat-value">{businesses.length}</div>
            <div className="stat-foot">Managed repositories</div>
          </div>
        </div>

        <section className="create-box">
          <h3>Create Entity</h3>
          <form className="create-form" onSubmit={onSubmitCreateEntity}>
            <div className="field-grid">
              <label>
                Name
                <input
                  name="name"
                  value={formData.name}
                  onChange={onFormChange}
                  required
                />
              </label>
              <label>
                PAN
                <input
                  name="pan"
                  value={formData.pan}
                  onChange={onFormChange}
                  placeholder="ABCDE1234F"
                />
              </label>
              <label>
                GSTIN
                <input
                  name="gstin"
                  value={formData.gstin}
                  onChange={onFormChange}
                  placeholder="29ABCDE1234F2Z5"
                />
              </label>
              <label>
                State
                <input
                  name="state"
                  value={formData.state}
                  onChange={onFormChange}
                />
              </label>
            </div>
            {Boolean(formErrors) && (
              <pre className="form-error">{JSON.stringify(formErrors, null, 2)}</pre>
            )}
            <button type="submit" className="btn" disabled={isCreating}>
              {isCreating ? "Creating..." : "Register New Entity"}
            </button>
          </form>
        </section>

        <div className="cards-grid">
          {businesses.length > 0 ? (
            businesses.map((business) => (
              <article key={business.id} className="business-card">
                <div className="business-header">
                  <div className="business-logo">B</div>
                  <div>
                    <h3>{business.name}</h3>
                    <span className="pill">{business.gstin || "No GSTIN"}</span>
                  </div>
                </div>
                <div className="business-metrics">
                  <div>
                    <p>Audit Vault</p>
                    <strong>{business.documents_count || 0} items</strong>
                  </div>
                  <div>
                    <p>Financial Year</p>
                    <strong>FY 2024-25</strong>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onOpenEntity?.(business.detail_url)}
                >
                  Open Entity
                </button>
              </article>
            ))
          ) : (
            <div className="empty-state">
              <h2>No entities found</h2>
              <p>
                Your business network is currently empty. Use the form above to create your first entity.
              </p>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
