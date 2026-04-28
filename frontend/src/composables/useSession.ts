import { ref, onMounted } from "vue";
import { createSession, getSessions } from "@/services/api";
import type { SessionResponse } from "@/types";

export function useSession() {
  const currentSession = ref<SessionResponse | null>(null);

  const handleSessionChange = (session: SessionResponse) => {
    currentSession.value = session;
    localStorage.setItem("session_token", session.token.access_token);
    localStorage.setItem("session_id", session.session_id);
  };

  const handleSessionDelete = (sessionId: string) => {
    if (currentSession.value?.session_id === sessionId) {
      currentSession.value = null;
      localStorage.removeItem("session_token");
      localStorage.removeItem("session_id");
    }
  };

  const ensureSession = async (
    sidebarRef?: { loadSessions: () => void } | null
  ): Promise<SessionResponse | null> => {
    if (currentSession.value) {
      localStorage.setItem(
        "session_token",
        currentSession.value.token.access_token
      );
      localStorage.setItem("session_id", currentSession.value.session_id);
      return currentSession.value;
    }

    try {
      const sessions = await getSessions();
      if (sessions.length > 0) {
        currentSession.value = sessions[0];
        localStorage.setItem("session_token", sessions[0].token.access_token);
        localStorage.setItem("session_id", sessions[0].session_id);
        return sessions[0];
      }

      const newSession = await createSession();
      currentSession.value = newSession;
      localStorage.setItem("session_token", newSession.token.access_token);
      localStorage.setItem("session_id", newSession.session_id);
      sidebarRef?.loadSessions();
      return newSession;
    } catch (error) {
      console.error("Failed to ensure session:", error);
      return null;
    }
  };

  const initSession = async () => {
    const savedSessionId = localStorage.getItem("session_id");
    if (savedSessionId) {
      try {
        const sessions = await getSessions();
        const saved = sessions.find((s) => s.session_id === savedSessionId);
        if (saved) {
          currentSession.value = saved;
        } else if (sessions.length > 0) {
          currentSession.value = sessions[0];
          localStorage.setItem("session_token", sessions[0].token.access_token);
          localStorage.setItem("session_id", sessions[0].session_id);
        }
      } catch {
        // ignore
      }
    }
  };

  onMounted(() => {
    initSession();
  });

  return {
    currentSession,
    handleSessionChange,
    handleSessionDelete,
    ensureSession,
    initSession,
  };
}
