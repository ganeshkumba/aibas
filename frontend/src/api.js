function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
  return "";
}

async function parseJson(response) {
  const data = await response.json();
  if (!response.ok) {
    const message = data?.errors || data?.detail || "Request failed";
    throw message;
  }
  return data;
}

export async function fetchCurrentUser() {
  const response = await fetch("/api/me/", { credentials: "same-origin" });
  return parseJson(response);
}

export async function fetchBusinesses() {
  const response = await fetch("/api/businesses/", { credentials: "same-origin" });
  return parseJson(response);
}

export async function createBusiness(payload) {
  const response = await fetch("/api/businesses/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}
