
import axios from "axios";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000",
  headers: {
    "Content-Type": "application/json",
  },
});

export async function startResearch(question) {
  const response = await api.post("/research", { question });
  return response.data;
}

export async function uploadDocument(file) {
  const formData = new FormData();
  // "file" must match the FastAPI parameter name in upload_document()
  formData.append("file", file);

  // Override the default JSON header, otherwise axios would
  // convert the FormData into JSON and the file would not be sent.
  const response = await api.post("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return response.data;
}

export async function getDocuments() {
  const response = await api.get("/documents");
  return response.data.documents;
}

export async function getSessions() {
  const response = await api.get("/sessions");
  return response.data.sessions;
}

export async function getSessionMessages(sessionId) {
  const response = await api.get(
    `/sessions/${sessionId}/messages`
  );

  return response.data.messages;
}

export async function deleteSession(sessionId) {
  const response = await api.delete(`/sessions/${sessionId}`);
  return response.data;
}

export async function renameSession(sessionId, title) {
  const response = await api.patch(`/sessions/${sessionId}`, {
    title,
  });

  return response.data;
}

export default api;
