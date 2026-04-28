<template>
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
</template>

<script setup lang="ts">
import type { SessionResponse } from "@/types";

defineProps<{
  currentSession: SessionResponse | null;
}>();
</script>

<style scoped>
.page-header {
  text-align: center;
  margin-bottom: 60px;
  animation: fadeInDown 0.8s ease-out;
  position: relative;
  z-index: 1;
}

.page-title {
  font-size: 64px;
  font-weight: 900;
  color: #fff;
  margin-bottom: 20px;
  text-shadow: 0 4px 8px rgba(0, 0, 0, 0.3), 0 8px 16px rgba(0, 0, 0, 0.2);
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
</style>
