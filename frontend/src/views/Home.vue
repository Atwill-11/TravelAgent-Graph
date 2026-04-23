<template>
  <div class="home-layout">
    <SessionSidebar
      ref="sidebarRef"
      :current-session-id="currentSession?.session_id"
      @session-change="handleSessionChange"
      @session-delete="handleSessionDelete"
    />

    <div class="home-container">
      <div class="bg-decoration">
        <div class="circle circle-1"></div>
        <div class="circle circle-2"></div>
        <div class="circle circle-3"></div>
      </div>

      <div class="page-header">
        <h1 class="page-title">智能旅行助手</h1>
        <p class="page-subtitle">
          基于AI的个性化旅行规划，让每一次出行都完美无忧
        </p>
        <div v-if="currentSession" class="current-session-info">
          <a-tag color="blue"
            >当前会话: {{ currentSession.name || "未命名会话" }}</a-tag
          >
        </div>
      </div>

      <a-card class="form-card" :bordered="false">
        <a-form :model="formData" layout="vertical" @finish="handleSubmit">
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">📍</span>
              <span class="section-title">目的地与日期</span>
            </div>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item
                  name="city"
                  :rules="[{ required: true, message: '请输入目的地城市' }]"
                >
                  <template #label
                    ><span class="form-label">目的地城市</span></template
                  >
                  <a-input
                    v-model:value="formData.city"
                    placeholder="例如: 北京"
                    size="large"
                    class="custom-input"
                  >
                    <template #prefix
                      ><span style="color: #1890ff">🏙️</span></template
                    >
                  </a-input>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item
                  name="start_date"
                  :rules="[{ required: true, message: '请选择开始日期' }]"
                >
                  <template #label
                    ><span class="form-label">开始日期</span></template
                  >
                  <a-date-picker
                    v-model:value="formData.start_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    placeholder="选择日期"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item
                  name="end_date"
                  :rules="[{ required: true, message: '请选择结束日期' }]"
                >
                  <template #label
                    ><span class="form-label">结束日期</span></template
                  >
                  <a-date-picker
                    v-model:value="formData.end_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    placeholder="选择日期"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item>
                  <template #label
                    ><span class="form-label">旅行天数</span></template
                  >
                  <div class="days-display-compact">
                    <span class="days-value">{{ formData.travel_days }}</span>
                    <span class="days-unit">天</span>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">⚙️</span>
              <span class="section-title">偏好设置</span>
            </div>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item name="transportation">
                  <template #label
                    ><span class="form-label">交通方式</span></template
                  >
                  <a-select
                    v-model:value="formData.transportation"
                    size="large"
                    class="custom-select"
                  >
                    <a-select-option value="公共交通"
                      >🚇 公共交通</a-select-option
                    >
                    <a-select-option value="自驾">🚗 自驾</a-select-option>
                    <a-select-option value="步行">🚶 步行</a-select-option>
                    <a-select-option value="混合">🔀 混合</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item name="accommodation">
                  <template #label
                    ><span class="form-label">住宿偏好</span></template
                  >
                  <a-select
                    v-model:value="formData.accommodation"
                    size="large"
                    class="custom-select"
                  >
                    <a-select-option value="经济型酒店"
                      >💰 经济型酒店</a-select-option
                    >
                    <a-select-option value="舒适型酒店"
                      >🏨 舒适型酒店</a-select-option
                    >
                    <a-select-option value="豪华酒店"
                      >⭐ 豪华酒店</a-select-option
                    >
                    <a-select-option value="民宿">🏡 民宿</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item name="preferences">
                  <template #label
                    ><span class="form-label">旅行偏好</span></template
                  >
                  <div class="preference-tags">
                    <a-checkbox-group
                      v-model:value="formData.preferences"
                      class="custom-checkbox-group"
                    >
                      <a-checkbox value="历史文化" class="preference-tag"
                        >🏛️ 历史文化</a-checkbox
                      >
                      <a-checkbox value="自然风光" class="preference-tag"
                        >🏞️ 自然风光</a-checkbox
                      >
                      <a-checkbox value="美食" class="preference-tag"
                        >🍜 美食</a-checkbox
                      >
                      <a-checkbox value="购物" class="preference-tag"
                        >🛍️ 购物</a-checkbox
                      >
                      <a-checkbox value="艺术" class="preference-tag"
                        >🎨 艺术</a-checkbox
                      >
                      <a-checkbox value="休闲" class="preference-tag"
                        >☕ 休闲</a-checkbox
                      >
                    </a-checkbox-group>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">💬</span>
              <span class="section-title">额外要求</span>
            </div>
            <a-form-item name="free_text_input">
              <a-textarea
                v-model:value="formData.free_text_input"
                placeholder="请输入您的额外要求，例如：想去看升旗、需要无障碍设施、对海鲜过敏等..."
                :rows="3"
                size="large"
                class="custom-textarea"
              />
            </a-form-item>
          </div>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              :loading="loading"
              :disabled="!currentSession"
              size="large"
              block
              class="submit-button"
            >
              <template v-if="!loading">
                <span class="button-icon">🚀</span>
                <span>{{
                  currentSession ? "开始规划我的旅行" : "请先选择或创建会话"
                }}</span>
              </template>
              <template v-else>
                <span>正在生成中...</span>
              </template>
            </a-button>
          </a-form-item>

          <a-form-item v-if="loading">
            <div class="loading-container">
              <a-progress
                :percent="loadingProgress"
                status="active"
                :stroke-color="{ '0%': '#667eea', '100%': '#764ba2' }"
                :stroke-width="10"
              />
              <p class="loading-status">{{ loadingStatus }}</p>
            </div>
          </a-form-item>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { generateTripPlan, createSession, getSessions } from "@/services/api";
import type { TripFormData, SessionResponse } from "@/types";
import type { Dayjs } from "dayjs";
import SessionSidebar from "@/components/SessionSidebar.vue";

const router = useRouter();
const loading = ref(false);
const loadingProgress = ref(0);
const loadingStatus = ref("");
const currentSession = ref<SessionResponse | null>(null);
const sidebarRef = ref<InstanceType<typeof SessionSidebar> | null>(null);

type HomeFormData = Omit<TripFormData, "start_date" | "end_date"> & {
  start_date: Dayjs | null;
  end_date: Dayjs | null;
};

const formData = reactive<HomeFormData>({
  city: "",
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: "公共交通",
  accommodation: "经济型酒店",
  preferences: [],
  free_text_input: "",
});

watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, "day") + 1;
    if (days > 0 && days <= 30) {
      formData.travel_days = days;
    } else if (days > 30) {
      message.warning("旅行天数不能超过30天");
      formData.end_date = null;
    } else {
      message.warning("结束日期不能早于开始日期");
      formData.end_date = null;
    }
  }
});

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

const ensureSession = async (): Promise<SessionResponse | null> => {
  if (currentSession.value) {
    localStorage.setItem(
      "session_token",
      currentSession.value.token.access_token,
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
    sidebarRef.value?.loadSessions();
    return newSession;
  } catch (error) {
    console.error("Failed to ensure session:", error);
    return null;
  }
};

const handleSubmit = async () => {
  if (!formData.start_date || !formData.end_date) {
    message.error("请选择日期");
    return;
  }

  if (!localStorage.getItem("access_token")) {
    message.warning("请先登录");
    router.push("/login");
    return;
  }

  const session = await ensureSession();
  if (!session) {
    message.error("无法获取会话，请刷新页面重试");
    return;
  }

  loading.value = true;
  loadingProgress.value = 0;
  loadingStatus.value = "正在初始化...";

  const progressInterval = setInterval(() => {
    if (loadingProgress.value < 90) {
      loadingProgress.value += 10;
      if (loadingProgress.value <= 30) {
        loadingStatus.value = "🔍 正在搜索景点...";
      } else if (loadingProgress.value <= 50) {
        loadingStatus.value = "🌤️ 正在查询天气...";
      } else if (loadingProgress.value <= 70) {
        loadingStatus.value = "🏨 正在推荐酒店...";
      } else {
        loadingStatus.value = "📋 正在生成行程计划...";
      }
    }
  }, 500);

  try {
    const requestData: TripFormData = {
      city: formData.city,
      start_date: formData.start_date.format("YYYY-MM-DD"),
      end_date: formData.end_date.format("YYYY-MM-DD"),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input,
    };

    const response = await generateTripPlan(
      requestData,
      session.token.access_token,
    );

    clearInterval(progressInterval);
    loadingProgress.value = 100;
    loadingStatus.value = "✅ 完成!";

    if (response.success && response.data) {
      sessionStorage.setItem("tripPlan", JSON.stringify(response.data));
      message.success("旅行计划生成成功!");
      setTimeout(() => {
        router.push("/result");
      }, 500);
    } else {
      message.error(response.message || "生成失败");
    }
  } catch (error: any) {
    clearInterval(progressInterval);
    message.error(error.message || "生成旅行计划失败，请稍后重试");
  } finally {
    setTimeout(() => {
      loading.value = false;
      loadingProgress.value = 0;
      loadingStatus.value = "";
    }, 1000);
  }
};

onMounted(async () => {
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
});
</script>

<style scoped>
.home-layout {
  display: flex;
  min-height: calc(100vh - 64px - 69px);
}

.home-container {
  flex: 1;
  background:
    linear-gradient(
      135deg,
      rgba(102, 126, 234, 0.95) 0%,
      rgba(118, 75, 162, 0.95) 50%,
      rgba(240, 147, 251, 0.9) 100%
    ),
    url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320"><path fill="%23ffffff" fill-opacity="0.05" d="M0,96L48,112C96,128,192,160,288,186.7C384,213,480,235,576,213.3C672,192,768,128,864,128C960,128,1056,192,1152,208C1248,224,1344,192,1392,176L1440,160L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path></svg>')
      bottom no-repeat;
  background-size:
    cover,
    100% 320px;
  padding: 60px 20px;
  position: relative;
  overflow: hidden;
}

.home-container::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    radial-gradient(
      circle at 20% 30%,
      rgba(120, 119, 198, 0.4) 0%,
      transparent 50%
    ),
    radial-gradient(
      circle at 80% 70%,
      rgba(252, 176, 69, 0.3) 0%,
      transparent 50%
    ),
    radial-gradient(
      circle at 50% 50%,
      rgba(102, 126, 234, 0.2) 0%,
      transparent 70%
    );
  pointer-events: none;
}

.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  animation: float 20s infinite ease-in-out;
  box-shadow: inset 0 0 80px rgba(255, 255, 255, 0.15);
}

.circle-1 {
  width: 400px;
  height: 400px;
  top: -150px;
  left: -150px;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.15) 0%,
    rgba(255, 255, 255, 0.05) 70%
  );
}
.circle-2 {
  width: 300px;
  height: 300px;
  top: 40%;
  right: -100px;
  animation-delay: 5s;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.12) 0%,
    rgba(255, 255, 255, 0.04) 70%
  );
}
.circle-3 {
  width: 250px;
  height: 250px;
  bottom: -80px;
  left: 25%;
  animation-delay: 10s;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.1) 0%,
    rgba(255, 255, 255, 0.03) 70%
  );
}

.circle::before {
  content: "";
  position: absolute;
  top: 15%;
  left: 15%;
  width: 25%;
  height: 25%;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 50%;
  filter: blur(20px);
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
  33% {
    transform: translateY(-30px) rotate(120deg) scale(1.05);
  }
  66% {
    transform: translateY(-15px) rotate(240deg) scale(0.95);
  }
}

.page-header {
  text-align: center;
  margin-bottom: 60px;
  animation: fadeInDown 0.8s ease-out;
  position: relative;
  z-index: 1;
}

.icon-wrapper {
  margin-bottom: 24px;
  position: relative;
  display: inline-block;
}

.icon-wrapper::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 120px;
  height: 120px;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.3) 0%,
    transparent 70%
  );
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

.icon {
  font-size: 90px;
  display: inline-block;
  animation: bounce 2s infinite;
  filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.3));
  position: relative;
  z-index: 1;
}

@keyframes pulse {
  0%,
  100% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.5;
  }
  50% {
    transform: translate(-50%, -50%) scale(1.2);
    opacity: 0.8;
  }
}

@keyframes bounce {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-25px);
  }
}

.page-title {
  font-size: 64px;
  font-weight: 900;
  color: #fff;
  margin-bottom: 20px;
  text-shadow:
    0 4px 8px rgba(0, 0, 0, 0.3),
    0 8px 16px rgba(0, 0, 0, 0.2);
  letter-spacing: 3px;
  background: linear-gradient(135deg, #fff 0%, #f0f0f0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  position: relative;
}

.page-subtitle {
  font-size: 22px;
  color: rgba(255, 255, 255, 0.98);
  margin: 0;
  font-weight: 400;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  letter-spacing: 1px;
}

.current-session-info {
  margin-top: 20px;
}

.current-session-info :deep(.ant-tag) {
  padding: 6px 16px;
  font-size: 14px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.3);
  backdrop-filter: blur(10px);
}

.form-card {
  max-width: 1200px;
  margin: 0 auto;
  border-radius: 28px;
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.4),
    0 15px 40px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  animation: fadeInUp 0.8s ease-out;
  position: relative;
  z-index: 1;
  backdrop-filter: blur(20px);
  background: rgba(255, 255, 255, 0.98) !important;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.form-card::before {
  content: "";
  position: absolute;
  top: -3px;
  left: -3px;
  right: -3px;
  bottom: -3px;
  background: linear-gradient(
    135deg,
    rgba(102, 126, 234, 0.4),
    rgba(118, 75, 162, 0.4),
    rgba(240, 147, 251, 0.4)
  );
  border-radius: 31px;
  z-index: -1;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.form-card:hover::before {
  opacity: 1;
}

.form-card :deep(.ant-card-body) {
  padding: 40px 48px;
}

.form-section {
  margin-bottom: 32px;
  padding: 28px 32px;
  background: linear-gradient(135deg, #fafbfc 0%, #ffffff 100%);
  border-radius: 20px;
  border: 2px solid #e8ecf0;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.form-section::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.form-section:hover {
  box-shadow:
    0 12px 32px rgba(102, 126, 234, 0.15),
    0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-3px);
  border-color: rgba(102, 126, 234, 0.3);
}

.form-section:hover::before {
  opacity: 1;
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #667eea 0%, #764ba2 100%) 1;
  position: relative;
}

.section-header::after {
  content: "";
  position: absolute;
  bottom: -3px;
  left: 0;
  width: 60px;
  height: 3px;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
}

.section-icon {
  font-size: 28px;
  margin-right: 14px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
}
.section-title {
  font-size: 20px;
  font-weight: 700;
  color: #333;
  letter-spacing: 0.5px;
}
.form-label {
  font-size: 15px;
  font-weight: 600;
  color: #444;
}

.custom-input :deep(.ant-input),
.custom-input :deep(.ant-picker) {
  border-radius: 14px;
  border: 2px solid #e0e4e8;
  transition: all 0.3s ease;
  background: #fafbfc;
}

.custom-input :deep(.ant-input:hover),
.custom-input :deep(.ant-picker:hover) {
  border-color: #667eea;
  background: #fff;
}

.custom-input :deep(.ant-input:focus),
.custom-input :deep(.ant-picker-focused) {
  border-color: #667eea;
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
  background: #fff;
}

.custom-select :deep(.ant-select-selector) {
  border-radius: 14px !important;
  border: 2px solid #e0e4e8 !important;
  transition: all 0.3s ease;
  background: #fafbfc !important;
}

.custom-select:hover :deep(.ant-select-selector) {
  border-color: #667eea !important;
  background: #fff !important;
}

.custom-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: #667eea !important;
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1) !important;
  background: #fff !important;
}

.days-display-compact {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 14px;
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.days-display-compact .days-value {
  font-size: 26px;
  font-weight: 800;
  margin-right: 6px;
}
.days-display-compact .days-unit {
  font-size: 15px;
  font-weight: 500;
}

.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
}

.preference-tag :deep(.ant-checkbox-wrapper) {
  margin: 0 !important;
  padding: 10px 18px;
  border: 2px solid #e0e4e8;
  border-radius: 24px;
  transition: all 0.3s ease;
  background: white;
  font-size: 14px;
  font-weight: 500;
}

.preference-tag :deep(.ant-checkbox-wrapper:hover) {
  border-color: #667eea;
  background: #f5f7ff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.preference-tag :deep(.ant-checkbox-wrapper-checked) {
  border-color: #667eea;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.custom-textarea :deep(.ant-input) {
  border-radius: 14px;
  border: 2px solid #e0e4e8;
  transition: all 0.3s ease;
  background: #fafbfc;
}

.custom-textarea :deep(.ant-input:hover) {
  border-color: #667eea;
  background: #fff;
}

.custom-textarea :deep(.ant-input:focus) {
  border-color: #667eea;
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
  background: #fff;
}

.submit-button {
  height: 60px;
  border-radius: 30px;
  font-size: 19px;
  font-weight: 700;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
  transition: all 0.3s ease;
  letter-spacing: 1px;
}

.submit-button:hover:not(:disabled) {
  transform: translateY(-3px);
  box-shadow: 0 15px 40px rgba(102, 126, 234, 0.5);
}

.submit-button:active:not(:disabled) {
  transform: translateY(-1px);
}

.submit-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.button-icon {
  margin-right: 10px;
  font-size: 20px;
}

.loading-container {
  margin-top: 16px;
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #fff 100%);
  border-radius: 16px;
  border: 2px solid #e0e4e8;
}

.loading-status {
  text-align: center;
  margin-top: 12px;
  color: #666;
  font-size: 14px;
  font-weight: 500;
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-40px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(40px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
