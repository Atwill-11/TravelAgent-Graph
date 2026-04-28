<template>
  <div class="thinking-process">
    <div class="thinking-header">
      <div class="thinking-title">
        <span class="thinking-icon">🤖</span>
        <span>智能助手思考中</span>
        <span class="thinking-dots" v-if="isRunning">
          <span class="dot">.</span>
          <span class="dot">.</span>
          <span class="dot">.</span>
        </span>
      </div>
      <a-tag v-if="isRunning" color="processing">运行中</a-tag>
      <a-tag v-else-if="hasError" color="error">出错</a-tag>
      <a-tag v-else color="success">完成</a-tag>
    </div>

    <div class="steps-timeline">
      <div
        v-for="(step, index) in steps"
        :key="step.id"
        class="step-item"
        :class="{
          'step-running': step.status === 'running',
          'step-completed': step.status === 'completed',
          'step-failed': step.status === 'failed',
          'step-pending': step.status === 'pending',
        }"
      >
        <div class="step-connector" v-if="index > 0">
          <div class="connector-line"></div>
        </div>

        <div class="step-indicator">
          <div class="indicator-icon" v-if="step.status === 'completed'">✓</div>
          <div
            class="indicator-icon spinning"
            v-else-if="step.status === 'running'"
          >
            ⟳
          </div>
          <div class="indicator-icon" v-else-if="step.status === 'failed'">
            ✗
          </div>
          <div class="indicator-icon pending" v-else>{{ index + 1 }}</div>
        </div>

        <div class="step-content">
          <div class="step-header">
            <span class="step-icon">{{ step.icon }}</span>
            <span class="step-name">{{ step.display_name }}</span>
            <span class="step-time">{{ formatTime(step.timestamp) }}</span>
          </div>
          <div class="step-message" v-if="step.message">
            <span
              class="message-text"
              :class="{ 'typing-effect': step.status === 'running' }"
            >
              {{ step.message }}
            </span>
          </div>
          <div class="step-details" v-if="step.details">
            <span class="details-text">{{ step.details }}</span>
          </div>
          <div
            class="plan-items"
            v-if="step.plan_items && step.plan_items.length > 0"
          >
            <div
              v-for="(item, idx) in step.plan_items"
              :key="idx"
              class="plan-item"
            >
              <span class="plan-item-icon">{{ item.icon }}</span>
              <span class="plan-item-name">{{ item.task }}</span>
              <a-tag size="small" color="blue">{{ item.type_display }}</a-tag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  steps: {
    id: string;
    node: string;
    display_name: string;
    icon: string;
    message: string;
    status: "running" | "completed" | "failed" | "pending";
    timestamp: number;
    details?: string;
    plan_items?: { task: string; icon: string; type_display: string }[];
  }[];
  isRunning: boolean;
  hasError: boolean;
}>();

const formatTime = (timestamp: number): string => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};
</script>

<style scoped>
.thinking-process {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  border: 1px solid #f0f0f0;
}

.thinking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.thinking-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.thinking-icon {
  font-size: 22px;
}

.thinking-dots {
  display: inline-flex;
  gap: 2px;
}

.thinking-dots .dot {
  animation: dotBlink 1.4s infinite;
  font-weight: bold;
  color: #1890ff;
}

.thinking-dots .dot:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dots .dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes dotBlink {
  0%,
  20% {
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

.steps-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.step-item {
  display: flex;
  gap: 16px;
  position: relative;
}

.step-connector {
  position: absolute;
  left: 15px;
  top: -4px;
  width: 2px;
  height: 20px;
}

.connector-line {
  width: 100%;
  height: 100%;
  background: #d9d9d9;
}

.step-completed .connector-line {
  background: #52c41a;
}

.step-running .connector-line {
  background: linear-gradient(180deg, #52c41a 0%, #1890ff 100%);
}

.step-indicator {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  z-index: 1;
}

.step-pending .step-indicator {
  background: #f5f5f5;
  color: #bfbfbf;
  border: 2px solid #d9d9d9;
}

.step-running .step-indicator {
  background: #e6f7ff;
  color: #1890ff;
  border: 2px solid #1890ff;
}

.step-completed .step-indicator {
  background: #f6ffed;
  color: #52c41a;
  border: 2px solid #52c41a;
}

.step-failed .step-indicator {
  background: #fff1f0;
  color: #ff4d4f;
  border: 2px solid #ff4d4f;
}

.indicator-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.indicator-icon.pending {
  font-size: 12px;
}

.step-content {
  flex: 1;
  padding-bottom: 16px;
  min-width: 0;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.step-icon {
  font-size: 16px;
}

.step-name {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.step-time {
  margin-left: auto;
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
}

.step-message {
  margin-top: 4px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 8px;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.step-running .step-message {
  background: #e6f7ff;
  color: #1890ff;
}

.step-completed .step-message {
  background: #f6ffed;
  color: #52c41a;
}

.step-failed .step-message {
  background: #fff1f0;
  color: #ff4d4f;
}

.message-text.typing-effect::after {
  content: "|";
  animation: cursorBlink 0.8s infinite;
  color: #1890ff;
}

@keyframes cursorBlink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

.step-details {
  margin-top: 4px;
  font-size: 12px;
  color: #999;
}

.plan-items {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f9f9f9;
  border-radius: 6px;
  font-size: 13px;
}

.plan-item-icon {
  font-size: 14px;
}

.plan-item-name {
  flex: 1;
  color: #555;
}
</style>
