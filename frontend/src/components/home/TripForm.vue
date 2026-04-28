<template>
  <a-card class="form-card" :bordered="false">
    <a-form :model="formData" layout="vertical" @finish="handleSubmit">
      <FormSection icon="📍" title="目的地与日期">
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
      </FormSection>

      <FormSection icon="⚙️" title="偏好设置">
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
                <a-select-option value="公共交通">🚇 公共交通</a-select-option>
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
                <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
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
      </FormSection>

      <FormSection icon="💬" title="额外要求">
        <a-form-item name="free_text_input">
          <a-textarea
            v-model:value="formData.free_text_input"
            placeholder="请输入您的额外要求，例如：想去看升旗、需要无障碍设施、对海鲜过敏等..."
            :rows="3"
            size="large"
            class="custom-textarea"
          />
        </a-form-item>
      </FormSection>

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

      <a-form-item v-if="loading && !useStreamMode">
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

      <a-form-item v-if="loading && useStreamMode">
        <ThinkingProcess
          :steps="thinkingSteps"
          :is-running="isThinkingRunning"
          :has-error="hasThinkingError"
        />
      </a-form-item>
    </a-form>
  </a-card>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { useTripForm } from "@/composables/useTripForm";
import { useTripSubmit } from "@/composables/useTripSubmit";
import type { SessionResponse } from "@/types";
import FormSection from "./FormSection.vue";
import ThinkingProcess from "@/components/ThinkingProcess.vue";

const props = defineProps<{
  currentSession: SessionResponse | null;
}>();

const emit = defineEmits<{
  (e: "submit"): void;
}>();

const router = useRouter();
const { formData, getRequestData } = useTripForm();
const {
  loading,
  loadingProgress,
  loadingStatus,
  thinkingSteps,
  isThinkingRunning,
  hasThinkingError,
  useStreamMode,
  startSubmit,
} = useTripSubmit();

const handleSubmit = async () => {
  if (!localStorage.getItem("access_token")) {
    message.warning("请先登录");
    router.push("/login");
    return;
  }

  const requestData = getRequestData();
  if (!requestData) return;

  if (!props.currentSession) {
    message.error("无法获取会话，请刷新页面重试");
    return;
  }

  emit("submit");
  await startSubmit(requestData, props.currentSession);
};

defineExpose({
  formData,
});
</script>

<style scoped>
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
