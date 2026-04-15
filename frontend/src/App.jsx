import React, { useEffect, useState } from "react";
import BusinessNetworkPage from "./pages/BusinessNetworkPage";
import { createBusiness, fetchBusinesses, fetchCurrentUser } from "./api";

export default function App() {
  const [user, setUser] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [formErrors, setFormErrors] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    pan: "",
    gstin: "",
    state: "",
  });

  useEffect(() => {
    async function bootstrap() {
      try {
        const [userResponse, businessesResponse] = await Promise.all([
          fetchCurrentUser(),
          fetchBusinesses(),
        ]);
        setUser(userResponse);
        setBusinesses(businessesResponse.businesses || []);
      } catch (error) {
        console.error("Failed to load dashboard data", error);
      } finally {
        setLoading(false);
      }
    }
    bootstrap();
  }, []);

  function onFormChange(event) {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  }

  async function onSubmitCreateEntity(event) {
    event.preventDefault();
    setFormErrors(null);
    setIsCreating(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(formData).map(([key, value]) => [key, value.trim()])
      );
      const created = await createBusiness(payload);
      setBusinesses((prev) => [created, ...prev]);
      setFormData({ name: "", pan: "", gstin: "", state: "" });
    } catch (error) {
      setFormErrors(error);
    } finally {
      setIsCreating(false);
    }
  }

  function onOpenEntity(url) {
    if (url) {
      window.location.href = url;
    }
  }

  if (loading) {
    return <div className="loading">Loading dashboard...</div>;
  }

  return (
    <BusinessNetworkPage
      user={user}
      businesses={businesses}
      formData={formData}
      formErrors={formErrors}
      isCreating={isCreating}
      onFormChange={onFormChange}
      onSubmitCreateEntity={onSubmitCreateEntity}
      onOpenEntity={onOpenEntity}
    />
  );
}
