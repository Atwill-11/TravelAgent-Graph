import { ref, computed } from "vue";

const userEmail = ref(localStorage.getItem("user_email") || "");
const accessToken = ref(localStorage.getItem("access_token") || "");

export function useAuth() {
  const isLoggedIn = computed(() => !!accessToken.value);

  const login = (email: string, token: string) => {
    userEmail.value = email;
    accessToken.value = token;
    localStorage.setItem("user_email", email);
    localStorage.setItem("access_token", token);
  };

  const logout = () => {
    userEmail.value = "";
    accessToken.value = "";
    localStorage.removeItem("access_token");
    localStorage.removeItem("session_token");
    localStorage.removeItem("session_id");
    localStorage.removeItem("user_email");
  };

  return {
    userEmail,
    accessToken,
    isLoggedIn,
    login,
    logout,
  };
}
