import axios from "axios";
import type {
  TripFormData,
  TripPlanResponse,
  LoginResponse,
  SessionResponse,
  UserResponse,
  ChatMessage,
  ChatResponse,
  SSEPlanEvent,
  SSEExecuteEvent,
  SSESummarizeEvent,
  SSEReviewEvent,
  SSEResumeRequest,
  SSEDoneEvent,
  SSEErrorEvent,
  SSEStartEvent,
} from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 分钟超时，用于支持复杂的旅行计划生成
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  if (!config.headers.Authorization) {
    const accessToken = localStorage.getItem("access_token");
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("session_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export async function registerUser(
  email: string,
  password: string,
): Promise<UserResponse> {
  const response = await apiClient.post<UserResponse>("/api/v1/auth/register", {
    email,
    password,
  });
  return response.data;
}

export async function loginUser(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);
  formData.append("grant_type", "password");

  const response = await apiClient.post<LoginResponse>(
    "/api/v1/auth/login",
    formData,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } },
  );
  return response.data;
}

export async function createSession(name?: string): Promise<SessionResponse> {
  const response = await apiClient.post<SessionResponse>(
    "/api/v1/auth/session",
    name ? new URLSearchParams({ name }) : undefined,
    name
      ? { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
      : undefined,
  );
  return response.data;
}

export async function getSessions(): Promise<SessionResponse[]> {
  const response = await apiClient.get<SessionResponse[]>(
    "/api/v1/auth/sessions",
  );
  return response.data;
}

export async function updateSessionName(
  sessionId: string,
  name: string,
): Promise<SessionResponse> {
  const formData = new URLSearchParams();
  formData.append("name", name);

  const response = await apiClient.patch<SessionResponse>(
    `/api/v1/auth/session/${sessionId}/name`,
    formData,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } },
  );
  return response.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/api/v1/auth/session/${sessionId}`);
}

export async function generateTripPlan(
  formData: TripFormData,
  sessionToken?: string,
): Promise<TripPlanResponse> {
  const token = sessionToken || localStorage.getItem("session_token");
  if (!token) {
    throw new Error("请先选择或创建会话");
  }

  try {
    const response = await apiClient.post<TripPlanResponse>(
      "/api/v1/trip/plan",
      formData,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || error.message || "生成旅行计划失败",
    );
  }
}

export async function sendChatMessage(
  messages: ChatMessage[],
  sessionToken?: string,
): Promise<ChatResponse> {
  const token = sessionToken || localStorage.getItem("session_token");
  if (!token) {
    throw new Error("请先选择或创建会话");
  }

  const response = await apiClient.post<ChatResponse>(
    "/api/v1/chatbot/chat",
    {
      messages,
    },
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );
  return response.data;
}

export async function sendChatStream(
  messages: ChatMessage[],
  onChunk: (content: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): Promise<void> {
  try {
    const token =
      localStorage.getItem("session_token") ||
      localStorage.getItem("access_token");

    const response = await fetch(`${API_BASE_URL}/api/v1/chatbot/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) return;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value, { stream: true });
      const lines = text.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) {
              onDone();
            } else if (data.content) {
              onChunk(data.content);
            }
          } catch {
            // skip invalid JSON
          }
        }
      }
    }
  } catch (error: any) {
    onError(error.message || "聊天请求失败");
  }
}

export type SSEEventHandlers = {
  onStart?: (data: SSEStartEvent) => void;
  onPlan?: (data: SSEPlanEvent) => void;
  onExecute?: (data: SSEExecuteEvent) => void;
  onSummarize?: (data: SSESummarizeEvent) => void;
  onReview?: (data: SSEReviewEvent) => void;
  onDone?: (data: SSEDoneEvent) => void;
  onError?: (data: SSEErrorEvent) => void;
};

export async function generateTripPlanStream(
  formData: TripFormData,
  handlers: SSEEventHandlers,
  maxRetries: number = 3,
): Promise<void> {
  const token =
    localStorage.getItem("session_token") ||
    localStorage.getItem("access_token");
  if (!token) {
    handlers.onError?.({ message: "请先选择或创建会话", success: false });
    return;
  }

  let retryCount = 0;

  const attempt = async (): Promise<void> => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/trip/plan/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `HTTP error! status: ${response.status}`,
        );
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("无法获取响应流");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);
              switch (currentEvent) {
                case "start":
                  handlers.onStart?.(data as SSEStartEvent);
                  break;
                case "plan":
                  handlers.onPlan?.(data as SSEPlanEvent);
                  break;
                case "execute":
                  handlers.onExecute?.(data as SSEExecuteEvent);
                  break;
                case "summarize":
                  handlers.onSummarize?.(data as SSESummarizeEvent);
                  break;
                case "review":
                  handlers.onReview?.(data as SSEReviewEvent);
                  break;
                case "done":
                  handlers.onDone?.(data as SSEDoneEvent);
                  break;
                case "error":
                  handlers.onError?.(data as SSEErrorEvent);
                  break;
              }
            } catch {
              // skip invalid JSON
            }
            currentEvent = "";
          }
        }
      }
    } catch (error: any) {
      if (retryCount < maxRetries) {
        retryCount++;
        const delay = Math.min(1000 * Math.pow(2, retryCount), 10000);
        await new Promise((resolve) => setTimeout(resolve, delay));
        return attempt();
      }
      handlers.onError?.({
        message: error.message || "流式请求失败",
        success: false,
      });
    }
  };

  await attempt();
}

export async function resumeTripPlanStream(
  resumeRequest: SSEResumeRequest,
  handlers: SSEEventHandlers,
): Promise<void> {
  const token =
    localStorage.getItem("session_token") ||
    localStorage.getItem("access_token");
  if (!token) {
    handlers.onError?.({ message: "请先选择或创建会话", success: false });
    return;
  }

  try {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/trip/plan/resume/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(resumeRequest),
      },
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(
        errorData?.detail || `HTTP error! status: ${response.status}`,
      );
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("无法获取响应流");
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6);
          try {
            const data = JSON.parse(jsonStr);
            switch (currentEvent) {
              case "start":
                handlers.onStart?.(data as SSEStartEvent);
                break;
              case "plan":
                handlers.onPlan?.(data as SSEPlanEvent);
                break;
              case "execute":
                handlers.onExecute?.(data as SSEExecuteEvent);
                break;
              case "summarize":
                handlers.onSummarize?.(data as SSESummarizeEvent);
                break;
              case "review":
                handlers.onReview?.(data as SSEReviewEvent);
                break;
              case "done":
                handlers.onDone?.(data as SSEDoneEvent);
                break;
              case "error":
                handlers.onError?.(data as SSEErrorEvent);
                break;
            }
          } catch {
            // skip invalid JSON
          }
          currentEvent = "";
        }
      }
    }
  } catch (error: any) {
    handlers.onError?.({
      message: error.message || "恢复规划请求失败",
      success: false,
    });
  }
}

export async function healthCheck(): Promise<any> {
  const response = await apiClient.get("/health");
  return response.data;
}

export default apiClient;
